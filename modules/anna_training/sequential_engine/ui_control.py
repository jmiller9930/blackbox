"""
Web/operator control plane for sequential learning — strict state machine + auditable transitions.

States: ``idle`` | ``running`` | ``paused`` | ``stopped``

**Valid transitions (deterministic; invalid requests return ``reason_code`` and do not mutate state):**

- **start** (body: ``start_mode`` = ``resume`` | ``new_run``, plus run config): ``idle`` → ``running``; ``stopped`` → ``running``; ``paused`` → ``running``. Rejected from ``running`` (``already_running``). ``new_run`` requires empty artifact dir for ``test_id`` or operator Reset first. ``resume`` requires same ``test_id`` and same calibration fingerprint as stored.
- **pause**: ``running`` → ``paused``. Rejected unless ``running`` (``not_running``).
- **stop**: ``running`` → ``stopped``; ``paused`` → ``stopped``. Rejected if not ``running``/``paused`` (``not_active``).
- **reset** (optional ``archive``, ``new_test_id``): ``idle`` | ``paused`` | ``stopped`` → ``idle``. Rejected from ``running`` (``must_stop_before_reset``). If ``archive`` and prior ``test_id`` had artifacts, copies tree to ``artifacts/_archive/<test_id>_<iso>/``; SQLite decision history is **not** deleted.
- **tick** (internal advance): only advances when ``ui_state == running``; updates cursor and artifacts; no implicit state change except via driver errors recorded in ``last_error``.

**Artifact / state rules:** Pause and stop preserve ``events_cursor_line``, on-disk artifacts, and SQLite rows. Stop is a clean operator boundary without archive. Reset clears control state to defaults (optionally preset ``new_test_id``), merges transition log for audit, archives file artifacts when requested — never silent history deletion.

The engine does not discover event IDs; the operator supplies ``events_file_path``.
``tick`` consumes the next slice of IDs from that file (forward-only cursor).
Every successful transition appends one entry to ``transition_log`` (``at_utc``, ``from``, ``to``, ``action``, ``trace_id``).
"""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from modules.anna_training.store import utc_now_iso

from .calibration_factory import load_and_validate_calibration
from .calibration_report import calibration_report_fingerprint
from .canonical_json import sha256_hex
from .decision_state import export_decision_snapshot
from .io_paths import default_artifacts_dir
from .ledger_pairs import count_paired_market_events
from .runtime_driver import run_sequential_learning_driver
from .sequential_persistence import load_last_sequential_decision

UiState = Literal["idle", "running", "paused", "stopped"]

SCHEMA_VERSION = "sequential_ui_control_v1"

_control_lock = threading.Lock()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_control_state_path() -> Path:
    return default_artifacts_dir() / "web_control" / "sequential_ui_state.json"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_control_state(path: Path | None = None) -> dict[str, Any]:
    p = path or default_control_state_path()
    if not p.is_file():
        return _default_control_state()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _default_control_state()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return _default_control_state()
    raw.setdefault("transition_log", [])
    raw.setdefault("events_cursor_line", 0)
    raw.setdefault("events_processed_total", 0)
    return raw


def _default_control_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ui_state": "idle",
        "test_id": "",
        "strategy_id": "",
        "calibration_path": "",
        "calibration_fingerprint": "",
        "events_file_path": "",
        "ledger_db_path": "",
        "market_db_path": "",
        "artifacts_dir": "",
        "events_cursor_line": 0,
        "last_processed_market_event_id": None,
        "last_tick_at": None,
        "last_tick_summary": None,
        "last_error": None,
        "last_sprt_decision": None,
        "events_processed_total": 0,
        "transition_log": [],
    }


def save_control_state(state: dict[str, Any], path: Path | None = None) -> None:
    p = path or default_control_state_path()
    _ensure_parent(p)
    body = dict(state)
    body["transition_log"] = list(body.get("transition_log") or [])[-200:]
    p.write_text(json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _log_transition(state: dict[str, Any], *, from_s: str, to_s: str, action: str) -> None:
    log = list(state.get("transition_log") or [])
    log.append(
        {
            "at_utc": utc_now_iso(),
            "from": from_s,
            "to": to_s,
            "action": action,
            "trace_id": str(uuid.uuid4()),
        }
    )
    state["transition_log"] = log[-200:]


def _read_event_lines(events_path: Path) -> list[str]:
    if not events_path.is_file():
        return []
    out: list[str] = []
    for ln in events_path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def compute_run_validation(st: dict[str, Any]) -> dict[str, Any]:
    """
    Post-start / status checklist: calibration + MAE, ledger pairs, event queue.

    Does not mutate state.
    """
    out: dict[str, Any] = {
        "calibration_loaded": False,
        "calibration_detail": None,
        "mae_path_valid": False,
        "mae_protocol_id": None,
        "paired_trades_available": False,
        "paired_trades_count": 0,
        "paired_trades_detail": None,
        "events_file_detail": None,
        "event_queue_ready": False,
        "events_remaining": 0,
        "event_processing_ready": False,
    }
    cp = (st.get("calibration_path") or "").strip()
    if not cp:
        out["calibration_detail"] = "calibration_path not set in control state"
        return out
    cal_path = Path(cp)
    if not cal_path.is_file():
        out["calibration_detail"] = f"calibration file not found: {cal_path}"
        return out
    try:
        report = load_and_validate_calibration(cal_path)
        out["calibration_loaded"] = True
        out["mae_path_valid"] = True
        out["mae_protocol_id"] = report.mae_protocol_id
    except Exception as e:
        out["calibration_detail"] = str(e)
        out["mae_path_valid"] = False
        return out

    sid = (st.get("strategy_id") or "").strip()
    ldb_s = (st.get("ledger_db_path") or "").strip()
    if not ldb_s:
        out["paired_trades_detail"] = "ledger_db_path not set — cannot verify paired trades in ledger"
    elif not sid:
        out["paired_trades_detail"] = "strategy_id not set"
    else:
        ldb = Path(ldb_s)
        if not ldb.is_file():
            out["paired_trades_detail"] = f"ledger database not found: {ldb}"
        else:
            n = count_paired_market_events(candidate_strategy_id=sid, db_path=ldb)
            out["paired_trades_count"] = n
            out["paired_trades_available"] = n > 0
            if n == 0:
                out["paired_trades_detail"] = (
                    "no market_event_id with both baseline and anna rows for this strategy_id"
                )

    ef = (st.get("events_file_path") or "").strip()
    if not ef:
        out["events_file_detail"] = "events_file_path not set"
    else:
        evp = Path(ef)
        if not evp.is_file():
            out["events_file_detail"] = f"events file not found: {evp}"
        else:
            lines = _read_event_lines(evp)
            cur = int(st.get("events_cursor_line") or 0)
            rem = max(0, len(lines) - cur)
            out["events_remaining"] = rem
            out["event_queue_ready"] = rem > 0

    ui = st.get("ui_state") or "idle"
    out["event_processing_ready"] = ui == "running" and out.get("event_queue_ready", False)

    return out


def _processing_signal_dict(st: dict[str, Any]) -> dict[str, Any]:
    ts = st.get("last_tick_summary")
    last_batch: int | None = None
    if isinstance(ts, dict):
        v = ts.get("events_processed")
        if v is not None:
            last_batch = int(v)
    total = int(st.get("events_processed_total") or 0)
    tick_at = st.get("last_tick_at")
    return {
        "last_processed_market_event_id": st.get("last_processed_market_event_id"),
        "last_processed_at_utc": tick_at,
        "events_processed_total": total,
        "last_batch_events_processed": last_batch,
        "has_processing_evidence": bool(total > 0 or tick_at),
    }


def control_start(
    *,
    start_mode: str,
    test_id: str,
    strategy_id: str,
    calibration_path: str,
    events_file_path: str,
    ledger_db_path: str = "",
    market_db_path: str = "",
    artifacts_dir: str = "",
    state_path: Path | None = None,
) -> dict[str, Any]:
    """
    Start: idle|stopped → running, or paused → running (resume).

    ``new_run``: requires no existing artifact dir for ``test_id`` OR operator ran Reset first.
    ``resume``: continues ``events_cursor_line`` for same ``test_id`` (must match stored config).
    """
    tid = (test_id or "").strip()
    sid = (strategy_id or "").strip()
    cp = (calibration_path or "").strip()
    ef = (events_file_path or "").strip()
    sm = (start_mode or "resume").strip().lower()
    if sm not in ("resume", "new_run"):
        return {"ok": False, "reason_code": "invalid_start_mode", "detail": "start_mode must be resume or new_run"}
    if not tid or not sid or not cp or not ef:
        return {"ok": False, "reason_code": "missing_required_fields", "detail": "test_id, strategy_id, calibration_path, events_file_path required"}
    cal = Path(cp)
    if not cal.is_file():
        return {"ok": False, "reason_code": "calibration_not_found", "path": cp}
    evp = Path(ef)
    if not evp.is_file():
        return {"ok": False, "reason_code": "events_file_not_found", "path": ef}

    with _control_lock:
        st = load_control_state(state_path)
        cur = st.get("ui_state") or "idle"
        if cur == "running":
            return {"ok": False, "reason_code": "already_running", "ui_state": cur}
        if cur not in ("idle", "stopped", "paused"):
            return {"ok": False, "reason_code": "invalid_state_for_start", "ui_state": cur}

        report = load_and_validate_calibration(cal)
        cf = sha256_hex(calibration_report_fingerprint(report))

        art = Path(artifacts_dir) if (artifacts_dir or "").strip() else default_artifacts_dir()
        test_dir = art / tid

        if sm == "new_run":
            if test_dir.is_dir() and any(test_dir.iterdir()):
                return {
                    "ok": False,
                    "reason_code": "artifacts_exist_for_test_id",
                    "detail": "Use Reset to archive, or choose a new test_id",
                    "path": str(test_dir),
                }
            st["events_cursor_line"] = 0
            st["last_processed_market_event_id"] = None
            st["events_processed_total"] = 0
        else:
            # resume
            if (st.get("test_id") or "") and st.get("test_id") != tid:
                return {
                    "ok": False,
                    "reason_code": "test_id_mismatch_resume",
                    "detail": "Stored test_id differs — use same test_id or new_run + fresh test_id after Reset",
                    "stored_test_id": st.get("test_id"),
                }
            if (st.get("calibration_fingerprint") or "") and st["calibration_fingerprint"] != cf:
                return {
                    "ok": False,
                    "reason_code": "calibration_mismatch",
                    "detail": "Calibration fingerprint differs from stored — new calibration requires new test_id or Reset",
                }

        prev = cur
        st["ui_state"] = "running"
        st["test_id"] = tid
        st["strategy_id"] = sid
        st["calibration_path"] = str(cal.resolve())
        st["calibration_fingerprint"] = cf
        st["events_file_path"] = str(evp.resolve())
        st["ledger_db_path"] = (ledger_db_path or "").strip()
        st["market_db_path"] = (market_db_path or "").strip()
        st["artifacts_dir"] = str(art.resolve()) if artifacts_dir else ""
        st["last_error"] = None
        _log_transition(st, from_s=prev, to_s="running", action=f"start:{sm}")
        save_control_state(st, state_path)
        rv = compute_run_validation(st)
        return {"ok": True, "ui_state": "running", "reason_code": "start_ok", "start_mode": sm, "run_validation": rv}


def control_pause(state_path: Path | None = None) -> dict[str, Any]:
    """Pause: running → paused. Preserves cursor and all artifacts."""
    with _control_lock:
        st = load_control_state(state_path)
        cur = st.get("ui_state") or "idle"
        if cur != "running":
            return {"ok": False, "reason_code": "not_running", "ui_state": cur}
        _log_transition(st, from_s=cur, to_s="paused", action="pause")
        st["ui_state"] = "paused"
        save_control_state(st, state_path)
        return {"ok": True, "ui_state": "paused", "reason_code": "pause_ok"}


def control_stop(state_path: Path | None = None) -> dict[str, Any]:
    """Stop: running|paused → stopped. Preserves artifacts; does not reset cursor."""
    with _control_lock:
        st = load_control_state(state_path)
        cur = st.get("ui_state") or "idle"
        if cur not in ("running", "paused"):
            return {"ok": False, "reason_code": "not_active", "ui_state": cur}
        _log_transition(st, from_s=cur, to_s="stopped", action="stop")
        st["ui_state"] = "stopped"
        save_control_state(st, state_path)
        return {"ok": True, "ui_state": "stopped", "reason_code": "stop_ok"}


def control_reset(
    *,
    archive: bool = True,
    new_test_id: str | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """
    Reset: idle|stopped|paused → idle with clean boundary.

    If ``archive`` and current ``test_id`` has artifacts, copy to ``_archive/<test_id>_<iso>/``.
    Does **not** delete SQLite history (anna_sequential_decision_runs).
    Requires ui_state != running.
    """
    with _control_lock:
        st = load_control_state(state_path)
        cur = st.get("ui_state") or "idle"
        if cur == "running":
            return {"ok": False, "reason_code": "must_stop_before_reset", "ui_state": cur}

        tid = (st.get("test_id") or "").strip()
        art = Path(st.get("artifacts_dir") or "") if (st.get("artifacts_dir") or "").strip() else default_artifacts_dir()

        if archive and tid:
            test_dir = art / tid
            if test_dir.is_dir() and any(test_dir.iterdir()):
                arch_root = art / "_archive"
                arch_root.mkdir(parents=True, exist_ok=True)
                dest = arch_root / f"{tid}_{utc_now_iso().replace(':', '-')}"
                shutil.copytree(test_dir, dest, dirs_exist_ok=False)

        st2 = _default_control_state()
        if (new_test_id or "").strip():
            st2["test_id"] = new_test_id.strip()
        _log_transition(st2, from_s=cur, to_s="idle", action="reset")
        # preserve transition log from before reset (append)
        old_log = list(st.get("transition_log") or [])
        st2["transition_log"] = (old_log + st2["transition_log"])[-200:]
        save_control_state(st2, state_path)
        return {
            "ok": True,
            "ui_state": "idle",
            "reason_code": "reset_ok",
            "archived_test_id": tid if archive and tid else None,
        }


def build_operator_status(
    *,
    state_path: Path | None = None,
    ledger_db_path: Path | None = None,
) -> dict[str, Any]:
    """Snapshot for WebUI: control file + sequential_state + last DB decision."""
    st = load_control_state(state_path)
    tid = (st.get("test_id") or "").strip()
    sid = (st.get("strategy_id") or "").strip()
    art = Path(st.get("artifacts_dir") or "") if (st.get("artifacts_dir") or "").strip() else default_artifacts_dir()
    snap: dict[str, Any] | None = None
    last_db: dict[str, Any] | None = None
    ldb = Path(st.get("ledger_db_path") or "") if (st.get("ledger_db_path") or "").strip() else ledger_db_path
    if tid:
        snap = export_decision_snapshot(tid, artifacts_dir=art)
    if sid:
        last_db = load_last_sequential_decision(sid, db_path=ldb)

    ev_path = Path(st.get("events_file_path") or "") if (st.get("events_file_path") or "").strip() else None
    total_events = len(_read_event_lines(ev_path)) if ev_path and ev_path.is_file() else 0

    return {
        "schema": "sequential_operator_status_v1",
        "ui_state": st.get("ui_state") or "idle",
        "test_id": tid or None,
        "strategy_id": sid or None,
        "calibration_path": st.get("calibration_path") or None,
        "calibration_fingerprint": st.get("calibration_fingerprint") or None,
        "events_file_path": st.get("events_file_path") or None,
        "events_cursor_line": int(st.get("events_cursor_line") or 0),
        "events_total_lines": total_events,
        "events_processed_total": int(st.get("events_processed_total") or 0),
        "last_processed_market_event_id": st.get("last_processed_market_event_id"),
        "last_tick_at": st.get("last_tick_at"),
        "last_tick_summary": st.get("last_tick_summary"),
        "last_error": st.get("last_error"),
        "last_sprt_decision": st.get("last_sprt_decision"),
        "processing_signal": _processing_signal_dict(st),
        "run_validation": compute_run_validation(st),
        "sequential_state_snapshot": snap,
        "last_decision_row": last_db,
        "transition_log_tail": (st.get("transition_log") or [])[-12:],
    }


def control_tick(
    *,
    max_events: int = 5,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Process up to ``max_events`` IDs from events file starting at cursor (only if ui_state == running)."""
    max_events = max(1, min(500, int(max_events)))
    with _control_lock:
        st = load_control_state(state_path)
        if st.get("ui_state") != "running":
            return {
                "ok": False,
                "reason_code": "not_running_tick_skipped",
                "ui_state": st.get("ui_state"),
            }

        tid = (st.get("test_id") or "").strip()
        sid = (st.get("strategy_id") or "").strip()
        cp = (st.get("calibration_path") or "").strip()
        ef = (st.get("events_file_path") or "").strip()
        if not tid or not sid or not cp or not ef:
            st["last_error"] = "incomplete_control_config"
            save_control_state(st, state_path)
            return {"ok": False, "reason_code": "incomplete_config"}

        lines = _read_event_lines(Path(ef))
        start = int(st.get("events_cursor_line") or 0)
        batch = lines[start : start + max_events]
        if not batch:
            st["last_tick_at"] = utc_now_iso()
            st["last_tick_summary"] = {"processed": 0, "reason": "no_more_events"}
            save_control_state(st, state_path)
            return {"ok": True, "processed": 0, "reason_code": "end_of_events"}

        cal = load_and_validate_calibration(Path(cp))
        art = Path(st.get("artifacts_dir") or "") if (st.get("artifacts_dir") or "").strip() else default_artifacts_dir()
        ldb = Path(st.get("ledger_db_path") or "") if (st.get("ledger_db_path") or "").strip() else None
        mdb = Path(st.get("market_db_path") or "") if (st.get("market_db_path") or "").strip() else None

        try:
            result = run_sequential_learning_driver(
                test_id=tid,
                strategy_id=sid,
                calibration=cal,
                market_event_ids=batch,
                ledger_db_path=ldb,
                market_db_path=mdb,
                artifacts_dir=art,
                write_hypothesis_bundle=False,
            )
        except Exception as e:
            st["last_error"] = str(e)
            st["last_tick_at"] = utc_now_iso()
            save_control_state(st, state_path)
            return {"ok": False, "reason_code": "driver_exception", "detail": str(e), "http_status_hint": 500}

        st["events_cursor_line"] = start + len(batch)
        st["last_processed_market_event_id"] = batch[-1]
        st["last_tick_at"] = utc_now_iso()
        st["last_error"] = None
        st["last_tick_summary"] = {
            "events_processed": result.get("events_processed"),
            "last_sprt": result.get("last_sprt"),
        }
        ls = result.get("last_sprt")
        if isinstance(ls, dict):
            st["last_sprt_decision"] = ls.get("decision")
        st["events_processed_total"] = int(st.get("events_processed_total") or 0) + len(batch)
        save_control_state(st, state_path)
        return {"ok": True, "reason_code": "tick_ok", "driver_result": result}
