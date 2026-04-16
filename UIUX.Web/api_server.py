#!/usr/bin/env python3
"""Minimal BLACK BOX UI truth API for /api/v1/*."""
from __future__ import annotations

import cgi
import gzip
import hmac
import io
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

HOST = "0.0.0.0"
PORT = 8080
ROOT = Path(os.environ.get("BLACKBOX_REPO_ROOT", "/repo"))
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# Match Karpathy / CLI: load repo .env so BLACKBOX_ANNA_TRAINING_DIR (and Jack/Ollama) align — otherwise the
# dashboard reads default data/runtime/anna_training while the school loop writes a path from .env.
try:
    from modules.anna_training.repo_env import apply_repo_dotenv

    apply_repo_dotenv(_REPO_ROOT)
except Exception:
    pass
ARTIFACTS = ROOT / "docs" / "working" / "artifacts"

# Context engine (Pillar 1) — operational store under BLACKBOX_CONTEXT_ROOT or data/context_engine
try:
    from modules.context_engine.status import build_context_engine_status, record_api_probe
except ImportError:
    build_context_engine_status = None  # type: ignore[assignment]
    record_api_probe = None  # type: ignore[assignment]
try:
    from modules.wallet import build_wallet_status_payload
except ImportError:
    build_wallet_status_payload = None  # type: ignore[assignment]
STATE_FILE = ARTIFACTS / "ui_runtime_state.json"
PYTH_STREAM_FILE = ARTIFACTS / "pyth_stream_status.json"
PYTH_RECENT_FILE = ARTIFACTS / "pyth_stream_recent.json"
PYTH_SAFETY_FILE = ARTIFACTS / "pyth_storage_safety.json"

ALLOWED_AGENTS = {"anna", "billy", "mia", "chris", "data"}
ALLOWED_ACTIONS = {"start", "pause", "stop", "restart", "reset", "check-in"}

# v1 training governance — product copy + API truth (Option A: provisional qualification, not durable trust).
V1_GOVERNANCE_CONTRACT: dict[str, Any] = {
    "contract_id": "blackbox_v1_training_semantics_2026",
    "advisor_artifact": "docs/working/v1_governance_contract_advisor.md",
    "pass_means": "qualified_provisional",
    "pass_operator_line": (
        "Gate PASS means thresholds met on the current paper ledger at evaluation time — "
        "usable with caution; not trusted across all conditions or future time."
    ),
    "promotion_means": "qualified_method_not_universal_approval",
    "post_pass_behavior": "no_automatic_execution_or_method_preference_change",
    "degradation": "manual_operator_review_no_auto_demotion_v1",
    "improvement_mechanism": "operator_directive_config_code",
    "naming": (
        "Avoid calling gate PASS a durable skill; reserve skill/capability language for a future lifecycle contract."
    ),
    "soft_reset_boundary": (
        "No hard reset required to adopt semantics. Optional soft reset: pick a reporting baseline (date or iteration) "
        "to separate pre- vs post-contract narratives, or evaluate new windows without wiping the ledger."
    ),
    "hard_reset_note": (
        "flush-runtime / wipe ledger only if you intentionally want a clean evidence file — not required for wording."
    ),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def ensure_state() -> dict[str, Any]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    state = load_json(STATE_FILE)
    if isinstance(state, dict):
        return state
    state = {
        "paper_enabled": True,
        "live_enabled": False,
        "runtime_state": "not_connected",
        "last_transition_at": None,
        "last_event_at": None,
        "write_success_rate_5m": None,
        "ledger_lag_seconds": None,
        "last_error_code": "ledger_not_wired",
    }
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def save_state(state: dict[str, Any]) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def latest_drift_doctor_report() -> tuple[dict[str, Any] | None, Path | None]:
    if not ARTIFACTS.exists():
        return None, None
    candidates = sorted(
        [p for p in ARTIFACTS.iterdir() if p.is_file() and "drift_doctor" in p.name.lower()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        parsed = load_json(path)
        if isinstance(parsed, dict):
            return parsed, path
    return None, candidates[0] if candidates else None


def ledger_health(state: dict[str, Any]) -> dict[str, Any]:
    lag = state.get("ledger_lag_seconds")
    rate = state.get("write_success_rate_5m")
    if rate is None or lag is None:
        health = "not_wired"
    elif rate >= 0.99 and lag <= 10:
        health = "healthy"
    elif rate >= 0.95 and lag <= 60:
        health = "degraded"
    elif lag > 60:
        health = "stalled"
    else:
        health = "error"
    return {
        "health": health,
        "last_event_at": state.get("last_event_at"),
        "write_success_rate_5m": rate,
        "ledger_lag_seconds": lag,
        "last_error_code": state.get("last_error_code"),
    }


def build_status() -> tuple[dict[str, Any], dict[str, Any]]:
    state = ensure_state()
    drift, drift_path = latest_drift_doctor_report()
    billy_conn = "connected" if isinstance(drift, dict) and drift.get("overall_ready") is True else "unknown"
    billy_reason = (
        str(drift.get("drift", {}).get("user_account_state"))
        if isinstance(drift, dict)
        else "no_drift_doctor_artifact"
    )

    seq_snapshot: dict[str, Any] = {}
    seq_ui = "idle"
    try:
        from modules.anna_training.sequential_engine.ui_control import build_operator_status

        seq_snapshot = build_operator_status()
        seq_ui = str(seq_snapshot.get("ui_state") or "idle").lower()
    except Exception:
        seq_ui = "idle"

    # Primary signal: sequential learning RUNNING → runtime RUNNING + ledger wired for dashboard truth.
    if seq_ui == "running":
        runtime_state = "running"
        reason_code = "sequential_learning_running"
        tick_at = seq_snapshot.get("last_tick_at") or now_iso()
        state["runtime_state"] = runtime_state
        state["last_transition_at"] = tick_at
        state["last_event_at"] = tick_at
        state["write_success_rate_5m"] = 1.0
        state["ledger_lag_seconds"] = 5
        state["last_error_code"] = None
        controls_enabled = True
    elif seq_ui == "paused":
        runtime_state = "paused"
        reason_code = "sequential_learning_paused"
        state["runtime_state"] = runtime_state
        controls_enabled = True
    elif billy_conn == "connected":
        runtime_state = "connected"
        reason_code = "runtime_connected_via_billy"
        state["runtime_state"] = runtime_state
        controls_enabled = True
    else:
        runtime_state = "not_connected"
        reason_code = "runtime_not_connected"
        state["runtime_state"] = runtime_state
        controls_enabled = False

    save_state(state)

    anna_conn = "connected" if seq_ui == "running" else "unknown"
    anna_reason = "sequential_learning_active" if seq_ui == "running" else "anna_runtime_probe_not_configured"
    anna_lifecycle = "running" if seq_ui == "running" else "unknown"

    runtime = {
        "runtime_state": runtime_state,
        "last_transition_at": state.get("last_transition_at"),
        "controls_enabled": controls_enabled,
        "paper_enabled": bool(state.get("paper_enabled", False)),
        "live_enabled": bool(state.get("live_enabled", False)),
        "reason_code": reason_code,
        "trace_id": str(uuid.uuid4()),
        "probe_artifact": str(drift_path.relative_to(ROOT)) if drift_path else None,
        "ledger": ledger_health(state),
        "sequential_learning": {
            "ui_state": seq_ui,
            "events_processed_total": int(seq_snapshot.get("events_processed_total") or 0),
            "events_total_lines": int(seq_snapshot.get("events_total_lines") or 0),
            "last_tick_at": seq_snapshot.get("last_tick_at"),
            "last_processed_market_event_id": seq_snapshot.get("last_processed_market_event_id"),
        },
    }

    def item(agent_id: str, label: str, conn: str, reason: str, lifecycle: str) -> dict[str, Any]:
        return {
            "agent_id": agent_id,
            "agent_label": label,
            "connectivity_state": conn,
            "lifecycle_state": lifecycle,
            "reason_code": reason,
            "last_check_in_at": drift.get("timestamp_utc") if agent_id == "billy" and isinstance(drift, dict) else None,
            "control_capabilities": {
                "start": False,
                "pause": False,
                "stop": False,
                "restart": False,
                "reset": False,
                "check_in": agent_id == "billy",
            },
        }

    agents = {
        "items": [
            item("anna", "Anna", anna_conn, anna_reason, anna_lifecycle),
            item("billy", "Billy", billy_conn, billy_reason, "on" if billy_conn == "connected" else "unknown"),
            item("mia", "Mia", "not_wired", "mia_not_wired", "not_wired"),
            item("chris", "Chris", "not_wired", "chris_not_wired", "not_wired"),
            item("data", "Data", "not_wired", "data_not_wired", "not_wired"),
        ],
        "trace_id": str(uuid.uuid4()),
    }
    return runtime, agents


def build_pyth_status() -> dict[str, Any]:
    stream = load_json(PYTH_STREAM_FILE)
    if not isinstance(stream, dict):
        stream = {}
    recent = load_json(PYTH_RECENT_FILE)
    if not isinstance(recent, dict):
        recent = {}
    safety = load_json(PYTH_SAFETY_FILE)
    if not isinstance(safety, dict):
        safety = {}

    status = str(stream.get("status") or stream.get("stream_state") or "unknown")
    reason = str(stream.get("reason_code") or "stream_status_unavailable")
    updated_at = stream.get("last_event_at") or stream.get("updated_at")
    stale_after = int(stream.get("stale_after_seconds") or 120)
    age_seconds = None
    dt = parse_iso(str(updated_at) if updated_at else None)
    if dt is not None:
        age_seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))

    sqlite_path = ROOT / "data" / "sqlite" / "market_data.db"
    resolved_path = sqlite_path.resolve() if sqlite_path.exists() else sqlite_path
    db_bytes = resolved_path.stat().st_size if resolved_path.exists() else 0
    fs = os.statvfs(str(resolved_path.parent if resolved_path.exists() else sqlite_path.parent))
    fs_total = fs.f_blocks * fs.f_frsize
    fs_avail = fs.f_bavail * fs.f_frsize
    fs_used = fs_total - (fs.f_bfree * fs.f_frsize)
    avail_ratio = (fs_avail / fs_total) if fs_total else 0.0
    max_db = int(safety.get("max_db_bytes") or (40 * 1024**3))
    target_db = int(safety.get("target_db_bytes") or int(max_db * 0.9))
    if db_bytes >= max_db or avail_ratio < 0.10:
        db_color, db_state = "red", "capacity_risk"
    elif db_bytes >= target_db or avail_ratio < 0.25:
        db_color, db_state = "yellow", "watch"
    else:
        db_color, db_state = "green", "healthy"

    return {
        "source": "pyth",
        "status": status,
        "reason_code": reason,
        "last_update_at": updated_at,
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after,
        "trace_id": str(uuid.uuid4()),
        "probe_artifact": str(PYTH_STREAM_FILE.relative_to(ROOT)),
        "db_storage": {
            "health_color": db_color,
            "health_state": db_state,
            "sqlite_path": str(sqlite_path),
            "sqlite_resolved_path": str(resolved_path),
            "db_bytes": db_bytes,
            "fs_total_bytes": fs_total,
            "fs_used_bytes": fs_used,
            "fs_avail_bytes": fs_avail,
            "max_db_bytes": max_db,
            "target_db_bytes": target_db,
            "avail_ratio": round(avail_ratio, 4),
        },
        "training_source": {
            "path": str(sqlite_path),
            "resolved_path": str(resolved_path),
            "table": "market_ticks",
            "symbol_filter": "SOL-PERP",
            "source_filter": "pyth_market_ticks_sqlite",
        },
        "recent_count": len((recent.get("items") or [])) if isinstance(recent, dict) else 0,
    }


def build_binance_ping() -> dict[str, Any]:
    """Live connectivity: ``GET https://api.binance.com/api/v3/ping`` from the API server host."""
    import time
    import urllib.error
    import urllib.request

    url = "https://api.binance.com/api/v3/ping"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "ok": True,
                "latency_ms": round(latency_ms, 2),
                "http_status": int(resp.status),
                "error": None,
                "url": url,
                "trace_id": str(uuid.uuid4()),
            }
    except urllib.error.HTTPError as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "ok": False,
            "latency_ms": round(latency_ms, 2),
            "http_status": int(e.code),
            "error": str(e.reason or e),
            "url": url,
            "trace_id": str(uuid.uuid4()),
        }
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "ok": False,
            "latency_ms": round(latency_ms, 2),
            "http_status": None,
            "error": str(e),
            "url": url,
            "trace_id": str(uuid.uuid4()),
        }


def build_anna_summary() -> dict[str, Any]:
    runtime, agents = build_status()
    pyth = build_pyth_status()
    anna = None
    for item in agents.get("items", []):
        if str(item.get("agent_id")).lower() == "anna":
            anna = item
            break
    pyth_status = str(pyth.get("status") or "unknown")
    training_state = "ready" if pyth_status in {"healthy", "connected"} else "degraded"
    src = pyth.get("training_source") if isinstance(pyth.get("training_source"), dict) else {}
    return {
        "agent_id": "anna",
        "connectivity_state": str((anna or {}).get("connectivity_state") or "unknown"),
        "runtime_state": str((anna or {}).get("lifecycle_state") or "unknown"),
        "reason_code": str((anna or {}).get("reason_code") or "anna_summary_unavailable"),
        "training": {
            "state": training_state,
            "reason_code": "pyth_feed_backing_training",
            "source_path": str(src.get("resolved_path") or src.get("path") or "--"),
            "table": str(src.get("table") or "--"),
            "filters": {
                "symbol": str(src.get("symbol_filter") or "--"),
                "source": str(src.get("source_filter") or "--"),
            },
        },
        "participation": {"state": "not_wired", "reason_code": "training_participation_control_not_wired"},
        "strategy": {"state": "not_wired", "reason_code": "strategy_inventory_not_wired"},
        "trace_id": str(uuid.uuid4()),
        "runtime_trace_id": runtime.get("trace_id"),
    }


def _training_engagement_payload(st: dict[str, Any], harness: dict[str, Any]) -> dict[str, Any]:
    """Human-readable training story for operators (skill practice + harness path per tick)."""
    sp = st.get("karpathy_last_skill_practice")
    sp = sp if isinstance(sp, dict) else {}
    deck = st.get("grade_12_skills_deck")
    deck = deck if isinstance(deck, dict) else {}
    focus = deck.get("current_focus_requirement") or deck.get("current_focus")

    bullets: list[str] = []
    bullets.append(
        "Each loop tick Anna refreshes Grade-12 gates and the skills deck, runs scheduled tool/skill "
        "practice, logs the learning cycle, and runs the school paper harness (analysis → execution request → Jack paper when configured)."
    )
    if sp.get("ran"):
        outcome = "passed" if sp.get("passed") else "did not pass"
        sid = sp.get("skill_id") or "skill"
        summ = (sp.get("summary") or "").strip()
        bullets.append(
            f"Last skill practice: {sid} — {outcome}"
            + (f" — {summ}" if summ else "")
            + "."
        )
    else:
        note = (sp.get("note") or "").strip()
        cf = sp.get("current_focus")
        tail = note or (f"Current deck focus: {cf!r}." if cf else "No drill this tick (often numeric cohort or deck complete).")
        bullets.append(f"Last tick — tool practice: none. {tail}")

    h_skipped = harness.get("skipped")
    h_err = harness.get("error")
    if h_skipped:
        bullets.append(f"Paper harness: stopped — {h_skipped}.")
    elif h_err:
        bullets.append(f"Paper harness: error — {h_err}.")
    elif harness.get("enabled") is False:
        bullets.append("Paper harness: off (ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK=0 or disabled).")
    elif harness.get("paper_logged") is True or (harness.get("jack_delegate") or {}).get("ok"):
        rid = harness.get("request_id") or "—"
        bullets.append(
            f"Paper harness: Anna produced a request and execution delegated (request {rid}). "
            "Check paper rows / attempts for fills."
        )
    elif harness.get("request_id"):
        bullets.append(
            f"Paper harness: Anna produced execution request {harness.get('request_id')} "
            "(analysis + handoff succeeded; see skipped/error above if Jack did not run)."
        )
    else:
        bullets.append(
            "Paper harness: no execution request this tick (observation-only or policy blocked — normal some ticks)."
        )

    plain = " ".join(bullets)
    return {
        "plain_english": plain,
        "bullets": bullets,
        "skills_deck_focus": focus,
        "skill_practice_last": sp,
    }


def build_anna_decision_trace_read(qs: dict[str, list[str]]) -> dict[str, Any]:
    """Read persisted decision_trace rows (exactly one filter: trade_id, trace_id, market_event_id, strategy_id)."""
    try:
        from modules.anna_training.decision_trace import (
            query_trace_by_trace_id,
            query_trace_by_trade_id,
            query_traces_by_market_event_id,
            query_traces_by_strategy_id,
        )
        from modules.anna_training.execution_ledger import default_execution_ledger_path
    except ImportError as e:
        return {
            "schema": "decision_trace_read_v1",
            "ok": False,
            "error": "import_failed",
            "detail": str(e),
        }

    def _one(name: str) -> str | None:
        v = (qs.get(name) or [None])[0]
        return (str(v) if v is not None else "").strip() or None

    trade_id = _one("trade_id")
    market_event_id = _one("market_event_id")
    strategy_id = _one("strategy_id")
    trace_id = _one("trace_id")

    n = sum(x is not None for x in (trade_id, market_event_id, strategy_id, trace_id))
    if n != 1:
        return {
            "schema": "decision_trace_read_v1",
            "ok": False,
            "error": "query_param",
            "detail": "Provide exactly one of: trade_id, market_event_id, strategy_id, trace_id",
        }

    raw = (os.environ.get("BLACKBOX_EXECUTION_LEDGER_PATH") or "").strip()
    db_path = Path(raw).expanduser() if raw else default_execution_ledger_path()

    try:
        if trade_id:
            tr = query_trace_by_trade_id(trade_id, db_path=db_path)
            return {
                "schema": "decision_trace_read_v1",
                "ok": True,
                "kind": "single",
                "trace": tr,
                "ledger_path": str(db_path),
            }
        if trace_id:
            tr = query_trace_by_trace_id(trace_id, db_path=db_path)
            return {
                "schema": "decision_trace_read_v1",
                "ok": True,
                "kind": "single",
                "trace": tr,
                "ledger_path": str(db_path),
            }
        if market_event_id:
            traces = query_traces_by_market_event_id(market_event_id, db_path=db_path)
            return {
                "schema": "decision_trace_read_v1",
                "ok": True,
                "kind": "list",
                "traces": traces,
                "ledger_path": str(db_path),
            }
        traces = query_traces_by_strategy_id(strategy_id or "", db_path=db_path)
        return {
            "schema": "decision_trace_read_v1",
            "ok": True,
            "kind": "list",
            "traces": traces,
            "ledger_path": str(db_path),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "schema": "decision_trace_read_v1",
            "ok": False,
            "error": "exception",
            "detail": str(e),
            "ledger_path": str(db_path),
        }


def build_anna_market_event_view(qs: dict[str, list[str]]) -> dict[str, Any]:
    """Aggregate event-centric JSON for operator UI (baseline vs Anna, traces, markers)."""
    try:
        from modules.anna_training.market_event_view import build_market_event_view

        return build_market_event_view(qs)
    except ImportError as e:
        return {
            "schema": "anna_market_event_view_v1",
            "ok": False,
            "error": "import_failed",
            "detail": str(e),
        }


def build_anna_operator_dashboard(qs: dict[str, list[str]]) -> dict[str, Any]:
    """Market-event view plus top-five selection, survival tests, lifecycle map (operator control surface)."""
    try:
        from modules.anna_training.operator_dashboard import build_operator_dashboard

        return build_operator_dashboard(qs)
    except ImportError as e:
        return {
            "schema": "anna_operator_dashboard_v1",
            "ok": False,
            "error": "import_failed",
            "detail": str(e),
        }


def build_anna_strategy_catalog() -> dict[str, Any]:
    try:
        from modules.anna_training.market_event_view import build_strategy_catalog_response

        return build_strategy_catalog_response()
    except ImportError as e:
        return {"schema": "anna_strategy_catalog_v1", "ok": False, "error": "import_failed", "detail": str(e)}


def build_anna_evaluation_summary(qs: dict[str, list[str]]) -> dict[str, Any]:
    """QEL judgment view — lifecycle, checkpoints (PASS/FAIL), condensed metrics (read-only)."""
    try:
        from modules.anna_training.evaluation_summary import build_evaluation_summary

        return build_evaluation_summary(qs)
    except ImportError as e:
        return {
            "schema": "anna_evaluation_summary_v1",
            "ok": False,
            "error": "import_failed",
            "detail": str(e),
        }


def build_anna_training_dashboard() -> dict[str, Any]:
    """Fixed-layout JSON for web UI: same facts as `anna status` / compact dashboard (read-only)."""
    tid = str(uuid.uuid4())
    try:
        from modules.anna_training.gates import evaluate_grade12_gates
        from modules.anna_training.paper_trades import (
            cohort_ledger_warnings,
            load_paper_trades_for_gates,
            summarize_trades,
            trades_path,
        )
        from modules.anna_training.store import anna_training_dir, load_state, state_path
        from modules.anna_training.trade_attempts import (
            attempts_path,
            load_trade_attempts,
            summarize_trade_activity,
        )
        from modules.anna_training.paper_judgment import (
            PAPER_JUDGMENT_BLURB,
            PAPER_LEDGER_AUTHORITATIVE_FOR_TRAINING,
        )
        from modules.anna_training.report_card_text import learning_signal_verdict
    except ImportError as e:
        return {
            "schema": "anna_training_dashboard_v1",
            "ok": False,
            "error": "import_failed",
            "detail": str(e),
            "trace_id": tid,
        }
    try:
        st = load_state()
        g12 = evaluate_grade12_gates()
        trades = load_paper_trades_for_gates()
        s = summarize_trades(trades)
        act = summarize_trade_activity()
        recent = sorted(trades, key=lambda x: x.get("ts_utc") or "", reverse=True)[:100]
        ph = st.get("karpathy_last_paper_harness")
        if isinstance(ph, dict):
            harness = ph
        else:
            harness = {}
        engagement = _training_engagement_payload(st, harness)
        snap = harness.get("analysis_snapshot")
        analysis_snapshot = snap if isinstance(snap, dict) else {}
        sp_last = st.get("karpathy_last_skill_practice")
        skill_practice_last = sp_last if isinstance(sp_last, dict) else {}
        deck = st.get("grade_12_skills_deck")
        deck = deck if isinstance(deck, dict) else {}
        ls = learning_signal_verdict(g12, st)
        att_rows = load_trade_attempts()
        recent_attempts = []
        for e in att_rows[-18:]:
            if not isinstance(e, dict):
                continue
            rid = e.get("request_id")
            recent_attempts.append(
                {
                    "ts_utc": str(e.get("ts_utc") or "")[:22],
                    "phase": e.get("phase"),
                    "status": e.get("status"),
                    "request_id": (str(rid)[:14] + "…") if rid and len(str(rid)) > 14 else rid,
                }
            )
        lp = st.get("karpathy_last_llm_preflight")
        llm_preflight = lp if isinstance(lp, dict) else {}
        dp = st.get("karpathy_last_data_preflight")
        data_preflight = dp if isinstance(dp, dict) else {}
        pol = st.get("karpathy_last_preflight_policy")
        preflight_policy = pol if isinstance(pol, dict) else {}

        semantics = {
            "loop_tick_means": (
                "Each supervisor tick: **data preflight** (Pyth stream + market_data.db; optional Solana) → "
                "**LLM probe** (GET Ollama /api/tags when ANNA_USE_LLM is on — informational in state/heartbeat) → "
                "then iteration++ → skills deck → tool drill when deck focus is a Grade-12 tool ID → paper harness "
                "(analyze_to_dict → execution request → Jack paper if BLACKBOX_JACK_EXECUTOR_CMD is set). "
                "A bad Ollama probe does not skip school; fix OLLAMA_BASE_URL / model for real LLM analysis."
            ),
            "attempt_log_vs_tick": (
                "The attempt log file counts delegate/manual events (jack_handoff, paper_manual, etc.) — "
                "not one line per tick. The harness still runs every tick; that is the repeated analysis "
                "and handoff attempt."
            ),
            "paper_ledger_vs_tick": (
                "Paper ledger rows append when a paper trade is logged to paper_trades.jsonl — not every tick."
            ),
            "scorecard_where_data_lives": (
                "W/L and P&L totals are every line in paper_trades.jsonl under paths.anna_training_dir "
                "(append-only). New trades add rows; old rows stay until flush-runtime --yes or you delete the file. "
                "The API loads repo .env so BLACKBOX_ANNA_TRAINING_DIR matches the Karpathy loop."
            ),
            "paper_judgment": PAPER_JUDGMENT_BLURB,
            "digest_ok_vs_trade_win": (
                "Training digest steps 1–4 use OK/YES for **pipeline** completion (analysis, request, delegate, row). "
                "That is different from **won** on a trade — use digest step 5 and the paper trades table for outcomes."
            ),
        }

        def _activity_feed() -> list[dict[str, Any]]:
            """Optional tail — excludes repetitive supervisor cycle lines; use digest for the real story."""
            out: list[dict[str, Any]] = []
            tick_ts = st.get("karpathy_loop_last_tick_utc")
            n = st.get("karpathy_loop_iteration")
            if tick_ts:
                out.append(
                    {
                        "ts_utc": str(tick_ts)[:24],
                        "tag": "tick",
                        "line": f"Supervisor tick #{n} (state updated)",
                    }
                )
            h = harness or {}
            if h.get("paper_logged") is True:
                rid = h.get("request_id")
                rid_s = (str(rid)[:12] + "…") if rid else "—"
                out.append(
                    {
                        "ts_utc": str(tick_ts or "")[:24],
                        "tag": "paper",
                        "line": f"Paper row written · req {rid_s}",
                    }
                )
            elif h.get("skipped"):
                out.append(
                    {
                        "ts_utc": str(tick_ts or "")[:24],
                        "tag": "skip",
                        "line": "Harness: " + str(h.get("skipped"))[:100],
                    }
                )
            elif h.get("error"):
                out.append(
                    {
                        "ts_utc": str(tick_ts or "")[:24],
                        "tag": "err",
                        "line": "Harness: " + str(h.get("error"))[:100],
                    }
                )
            sp = skill_practice_last
            if isinstance(sp, dict) and sp.get("ran"):
                sk = sp.get("skill_id") or "tool"
                pf = "PASS" if sp.get("passed") else "no"
                out.append(
                    {
                        "ts_utc": str(tick_ts or "")[:24],
                        "tag": "drill",
                        "line": f"Tool drill · {sk} · {pf}",
                    }
                )
            skip_kinds = frozenset({"karpathy_learning_cycle_v1", "karpathy_skill_practice_v1"})
            log = list(st.get("cumulative_learning_log") or [])
            for e in reversed(log[-24:]):
                if not isinstance(e, dict):
                    continue
                kind = str(e.get("kind") or "")
                if kind in skip_kinds:
                    continue
                ts = str(e.get("ts_utc") or "")[:24]
                sumy = str(e.get("summary") or "").replace("\n", " ")[:110]
                if sumy:
                    out.append({"ts_utc": ts, "tag": kind[:24] or "log", "line": sumy})
            out.sort(key=lambda x: str(x.get("ts_utc") or ""), reverse=True)
            return out[:16]

        def _training_run_digest() -> dict[str, Any]:
            """Single stitched view: Grade-12 bar + ordered steps for the last harness save."""
            h = harness or {}
            snap = analysis_snapshot if isinstance(analysis_snapshot, dict) else {}
            tick_ts = st.get("karpathy_loop_last_tick_utc")
            n = st.get("karpathy_loop_iteration")
            why: list[str] = []
            if not g12.get("pass"):
                for b in (g12.get("blockers") or [])[:6]:
                    why.append(str(b)[:280])

            steps: list[dict[str, str]] = []
            err = str(h.get("error") or "")

            if "analyze_to_dict" in err:
                steps.append(
                    {
                        "step": "1 · Anna analysis",
                        "result": "FAIL",
                        "detail": err[:260],
                    }
                )
            elif snap:
                hl = (snap.get("interpretation_headline") or "").strip() or "(no headline)"
                src = snap.get("answer_source") or "—"
                intent = snap.get("suggested_intent") or "—"
                steps.append(
                    {
                        "step": "1 · Anna analysis",
                        "result": "OK",
                        "detail": f"{hl[:130]} · answer_source={src} · suggested_intent={str(intent)[:72]}",
                    }
                )
            else:
                steps.append(
                    {
                        "step": "1 · Anna analysis",
                        "result": "—",
                        "detail": "No analysis snapshot on last harness save (harness may not have completed analysis).",
                    }
                )

            sk = h.get("skipped")
            if sk == "analysis_preflight_blocked_body":
                steps.append(
                    {
                        "step": "2 · Execution request",
                        "result": "BLOCKED",
                        "detail": "Analysis blocked by preflight policy on body.",
                    }
                )
            elif sk == "no_execution_request":
                steps.append(
                    {
                        "step": "2 · Execution request",
                        "result": "NO",
                        "detail": str(h.get("detail") or "Observation-only or policy — no handoff to trade path.")[:220],
                    }
                )
            elif h.get("pending"):
                steps.append(
                    {
                        "step": "2 · Execution request",
                        "result": "PENDING",
                        "detail": "Auto paper off — approve + run_execution manually.",
                    }
                )
            elif h.get("request_id"):
                steps.append(
                    {
                        "step": "2 · Execution request",
                        "result": "YES",
                        "detail": f"request_id={str(h.get('request_id'))[:20]}…",
                    }
                )
            else:
                steps.append(
                    {
                        "step": "2 · Execution request",
                        "result": "—",
                        "detail": "No request_id in last harness state.",
                    }
                )

            jack_sk = sk and ("JACK" in str(sk).upper() or "jack" in str(sk).lower())
            if jack_sk:
                steps.append(
                    {
                        "step": "3 · Run execution → delegate",
                        "result": "BLOCKED",
                        "detail": str(sk)[:240],
                    }
                )
            elif "approve_request" in err or "approve" in err.lower():
                steps.append(
                    {
                        "step": "3 · Approve + run_execution",
                        "result": "FAIL",
                        "detail": err[:240],
                    }
                )
            elif "run_execution" in err:
                steps.append(
                    {
                        "step": "3 · run_execution",
                        "result": "FAIL",
                        "detail": err[:240],
                    }
                )
            elif h.get("execution_status"):
                jd = h.get("jack_delegate") if isinstance(h.get("jack_delegate"), dict) else {}
                pl = h.get("paper_logged")
                ex = h.get("execution_status")
                jerr = jd.get("error") if jd else None
                tail = f"execution_status={ex} · paper_logged={pl}"
                if jerr:
                    tail += f" · delegate: {str(jerr)[:100]}"
                ok = ex == "executed" and pl is True
                steps.append(
                    {
                        "step": "3 · run_execution → delegate",
                        "result": "OK" if ok else ("PARTIAL" if ex == "executed" else str(ex).upper()[:12]),
                        "detail": tail[:260],
                    }
                )
            elif h.get("request_id") and not jack_sk:
                steps.append(
                    {
                        "step": "3 · run_execution → delegate",
                        "result": "—",
                        "detail": "Request existed but no execution_status on last save (check daemon).",
                    }
                )
            else:
                steps.append(
                    {
                        "step": "3 · run_execution → delegate",
                        "result": "SKIPPED",
                        "detail": "Stopped before mock execution (no path or earlier skip).",
                    }
                )

            if h.get("paper_logged") is True:
                steps.append(
                    {
                        "step": "4 · Paper ledger",
                        "result": "YES",
                        "detail": "Row appended to paper_trades.jsonl (pipeline). This is not a ‘win’ — see step 5 / table for won|lost.",
                    }
                )
            else:
                steps.append(
                    {
                        "step": "4 · Paper ledger",
                        "result": "NO",
                        "detail": "No new paper row this tick (blocked earlier or delegate did not log).",
                    }
                )

            if recent:
                lt = recent[0]
                r0 = str(lt.get("result") or "").strip().upper() or "—"
                pnl_v = lt.get("pnl_usd")
                pnl_s = f"{float(pnl_v):.2f}" if pnl_v is not None else "—"
                steps.append(
                    {
                        "step": "5 · Trade outcome (ledger)",
                        "result": r0,
                        "detail": f"Most recent row: result={r0.lower() if r0 != '—' else '—'} · pnl_usd={pnl_s} — this is the scored outcome, not pipeline OK/YES above.",
                    }
                )
            else:
                steps.append(
                    {
                        "step": "5 · Trade outcome (ledger)",
                        "result": "—",
                        "detail": "No paper rows yet — W/L below will populate when trades log.",
                    }
                )

            gp_digest = bool(g12.get("pass"))
            bar_title = (
                "Grade-12 gate: QUALIFIED (provisional)"
                if gp_digest
                else "Grade-12 gate: NOT QUALIFIED"
            )
            bar_sub = (
                "v1 governance: thresholds met on current cohort snapshot — not durable trust across environments "
                "or regimes; drift is possible without auto-demotion."
                if gp_digest
                else "v1 governance: gate not satisfied; improvement is operator/config-driven. "
                "No hard reset required to adopt contract semantics — see Governance panel."
            )
            return {
                "grade12_pass": gp_digest,
                "grade12_bar_title": bar_title,
                "grade12_bar_subtitle": bar_sub,
                "why_grade12_not_pass": why,
                "last_tick_at": str(tick_ts) if tick_ts else None,
                "last_iteration": n,
                "digest_note": (
                    "Steps 1–4 are **pipeline health** (did school wiring run). **OK / YES** means that stage completed — "
                    "not that the market trade was profitable. **Step 5** and the paper table show won / lost / breakeven."
                ),
                "steps": steps,
            }

        activity_feed = _activity_feed()
        training_run_digest = _training_run_digest()

        return {
            "schema": "anna_training_dashboard_v1",
            "ok": True,
            "trace_id": tid,
            "at_utc": now_iso(),
            "paper_judgment": {
                "ledger_authoritative_for_training": PAPER_LEDGER_AUTHORITATIVE_FOR_TRAINING,
                "plain_english": PAPER_JUDGMENT_BLURB,
            },
            "semantics": semantics,
            "v1_governance_contract": dict(V1_GOVERNANCE_CONTRACT),
            "data_preflight": data_preflight,
            "preflight_policy": preflight_policy,
            "llm_preflight": llm_preflight,
            "training_engagement": engagement,
            "analysis_snapshot": analysis_snapshot,
            "skill_practice_last": skill_practice_last,
            "skills_deck_focus": deck.get("current_focus_requirement") or deck.get("current_focus"),
            "learning_signal": {
                "verdict": ls.get("verdict"),
                "headline": ls.get("headline"),
                "detail": (ls.get("detail") or "")[:280],
            },
            "activity_feed": activity_feed,
            "training_run_digest": training_run_digest,
            "attempt_events_recent": recent_attempts,
            "enrollment": {
                "curriculum_id": st.get("curriculum_id"),
                "training_method_id": st.get("training_method_id"),
            },
            "paths": {
                "anna_training_dir": str(anna_training_dir()),
                "state_json": str(state_path()),
                "paper_trades_jsonl": str(trades_path()),
                "attempts_jsonl": str(attempts_path()),
                "heartbeat_jsonl": str(anna_training_dir() / "karpathy_loop_heartbeat.jsonl"),
            },
            "loop": {
                "karpathy_loop_iteration": st.get("karpathy_loop_iteration"),
                "karpathy_loop_last_tick_utc": st.get("karpathy_loop_last_tick_utc"),
            },
            "gates": {
                "pass": bool(g12.get("pass")),
                "pass_label_v1": (
                    "QUALIFIED (provisional)" if g12.get("pass") else "NOT QUALIFIED"
                ),
                "curriculum_tools_pass": bool(g12.get("curriculum_tools_pass")),
                "numeric_gate_pass": bool(g12.get("numeric_gate_pass")),
                "cohort_vacuous_all_wins_zero_pnl": bool(g12.get("cohort_vacuous_all_wins_zero_pnl")),
                "decisive_trades": g12.get("decisive_trades"),
                "min_decisive_trades": g12.get("min_decisive_trades"),
                "win_rate": g12.get("win_rate"),
                "total_pnl_usd": g12.get("total_pnl_usd"),
                "paper_goal_met": g12.get("paper_goal_met"),
                "paper_goal_rationale": g12.get("paper_goal_rationale"),
                "blockers": [str(b)[:300] for b in (g12.get("blockers") or [])[:8]],
            },
            "paper_cohort": {
                "row_count": s.trade_count,
                "wins": s.wins,
                "losses": s.losses,
                "total_pnl_usd": s.total_pnl_usd,
                "warnings": cohort_ledger_warnings(s, trades),
            },
            "attempts": {
                "total_events": act.total_events,
                "uncategorized": act.uncategorized,
                "phase_status_counts": act.phase_status_counts,
                "jack_delegate_started": act.jack_delegate_started,
                "jack_delegate_failed": act.jack_delegate_failed,
                "jack_ok_with_paper": act.jack_delegate_ok_with_paper,
                "jack_ok_no_paper": act.jack_delegate_ok_no_paper,
                "paper_manual_recorded": act.paper_manual_recorded,
                "execution_blocked": act.execution_blocked,
                "failed_or_blocked": act.failed_or_blocked,
            },
            "paper_harness_last": harness,
            "recent_trades": recent,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "schema": "anna_training_dashboard_v1",
            "ok": False,
            "error": "build_failed",
            "detail": str(e),
            "trace_id": tid,
        }


def normalize_status(raw: Any) -> str:
    v = str(raw or "unknown").strip().lower()
    if v in {"healthy", "degraded", "error", "unknown"}:
        return v
    if v in {"connected", "up", "on", "ready", "ok"}:
        return "healthy"
    if v in {"running"}:
        return "healthy"
    if v in {"paused"}:
        return "degraded"
    if v in {"idle", "stopped"}:
        return "degraded"
    if v in {"warning", "watch", "not_connected", "partial", "stale"}:
        return "degraded"
    if v in {"disconnected", "down", "off", "capacity_risk", "failed", "failure"}:
        return "error"
    return "unknown"


def _fix(headline: str, steps: list[str], commands: list[str] | None = None, docs: list[str] | None = None) -> dict[str, Any]:
    return {
        "headline": headline,
        "steps": steps,
        "commands": commands or [],
        "docs": docs or [],
    }


def build_system_status() -> dict[str, Any]:
    runtime, agents = build_status()
    pyth = build_pyth_status()

    runtime_raw = runtime.get("runtime_state")
    control_status = normalize_status(runtime_raw)
    control_reason = str(runtime.get("reason_code") or "CONTROL_PLANE_STATUS_UNAVAILABLE")

    pyth_raw = pyth.get("status")
    data_status = normalize_status(pyth_raw)
    data_reason = str(pyth.get("reason_code") or "DATA_PLANE_STATUS_UNAVAILABLE")

    ui_api_status = "healthy"
    ui_api_reason = "STATUS_ENDPOINT_RESPONDING"

    agent_items = (agents.get("items") if isinstance(agents, dict) else None) or []
    agent_statuses: list[str] = []
    agents_node: dict[str, Any] = {}

    for item in agent_items:
        agent_id = str(item.get("agent_id") or "").lower()
        if agent_id not in ALLOWED_AGENTS:
            continue
        conn = item.get("connectivity_state") or item.get("lifecycle_state") or item.get("status")
        st = normalize_status(conn)
        reason = str(item.get("reason_code") or "AGENT_STATUS_UNAVAILABLE")
        summary = str(conn or "unknown")
        route = f"#agent-section-{agent_id}"
        label = f"{agent_id.capitalize()} workspace"
        agent_statuses.append(st)
        agents_node[agent_id] = {
            "status": st,
            "reason_code": reason,
            "summary": summary,
            "last_heartbeat_at": item.get("last_check_in_at"),
            "workspace_route": route,
            "workspace_label": label,
        }

    for required_id in sorted(ALLOWED_AGENTS):
        if required_id not in agents_node:
            agents_node[required_id] = {
                "status": "unknown",
                "reason_code": "AGENT_NODE_MISSING",
                "summary": "agent node missing from source",
                "last_heartbeat_at": None,
                "workspace_route": "",
                "workspace_label": f"{required_id.capitalize()} workspace",
            }
            agent_statuses.append("unknown")

    if any(st == "error" for st in agent_statuses):
        workers_status = "error"
    elif any(st == "degraded" for st in agent_statuses):
        workers_status = "degraded"
    elif all(st == "unknown" for st in agent_statuses):
        workers_status = "unknown"
    elif all(st == "healthy" for st in agent_statuses):
        workers_status = "healthy"
    else:
        workers_status = "degraded"

    plane_statuses = [control_status, data_status, ui_api_status, workers_status]
    if any(st == "error" for st in plane_statuses):
        top_status = "error"
    elif any(st == "degraded" for st in plane_statuses):
        top_status = "degraded"
    elif all(st == "unknown" for st in plane_statuses):
        top_status = "unknown"
    elif all(st == "healthy" for st in plane_statuses):
        top_status = "healthy"
    else:
        top_status = "unknown"

    now = now_iso()
    nodes = {
        "control_plane": {
            "status": control_status,
            "reason_code": control_reason,
            "summary": f"Runtime state {runtime_raw or 'unknown'}",
            "last_heartbeat_at": runtime.get("last_transition_at"),
            "fix": _fix(
                "Restore control-plane connectivity",
                ["Check runtime source artifact", "Reconcile drift/engine prerequisites", "Retry runtime probe"],
                ["python3 scripts/trading/drift_doctor.ts"],
                ["docs/working/current_directive.md"],
            ),
        },
        "data_plane": {
            "status": data_status,
            "reason_code": data_reason,
            "summary": f"Pyth status {pyth_raw or 'unknown'}",
            "last_heartbeat_at": pyth.get("last_update_at"),
            "fix": _fix(
                "Restore data-plane ingestion",
                ["Check pyth-stream container", "Verify stream status artifacts", "Confirm sqlite storage path and rails"],
                ["cd UIUX.Web && docker compose ps", "cd UIUX.Web && docker compose logs pyth-stream --tail 120"],
                ["scripts/trading/pyth_stream_probe.py"],
            ),
        },
        "ui_api": {
            "status": ui_api_status,
            "reason_code": ui_api_reason,
            "summary": "System status endpoint responding",
            "last_heartbeat_at": now,
            "fix": _fix(
                "Restore UI/API bridge",
                ["Verify nginx /api/v1 proxy", "Verify api container health", "Rebuild web stack"],
                ["cd UIUX.Web && docker compose up -d --build"],
                ["UIUX.Web/nginx/default.conf", "UIUX.Web/docker-compose.yml"],
            ),
        },
        "agent_workers": {
            "status": workers_status,
            "reason_code": "AGENT_WORKER_ROLLUP",
            "summary": "Aggregate from all required agent nodes",
            "last_heartbeat_at": now,
            "fix": _fix(
                "Bring missing or degraded agents to expected state",
                ["Open each agent workspace", "Review reason codes", "Wire missing routes/probes"],
                [],
                ["UIUX.Web/internal.html"],
            ),
        },
        "agents": agents_node,
    }

    return {
        "status": top_status,
        "reason_code": "SYSTEM_ROLLUP_FROM_PLANES",
        "last_updated_at": now,
        "nodes": nodes,
    }


def run_control(agent_id: str, action: str) -> tuple[str, str]:
    if agent_id in {"mia", "chris", "data"}:
        return "rejected", "not_wired"
    if agent_id == "anna":
        return "rejected", "anna_control_not_wired"
    if action == "check-in":
        drift, _ = latest_drift_doctor_report()
        return ("accepted", "billy_check_in_ok") if isinstance(drift, dict) and drift.get("overall_ready") else ("rejected", "billy_check_in_failed")
    return "rejected", "billy_control_not_wired"


TRAINING_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Anna training — live</title>
  <style>
    :root { --bg:#0d1117; --card:#161b22; --text:#e6edf3; --muted:#8b949e; --ok:#3fb950; --bad:#f85149; --accent:#58a6ff; }
    * { box-sizing: border-box; }
    body { font-family: ui-sans-serif, system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1rem; }
    h1 { font-size: 1.15rem; font-weight: 600; margin: 0 0 0.35rem; }
    .lead { font-size: 0.8rem; color: var(--muted); margin: 0 0 1rem; max-width: 52rem; line-height: 1.45; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; }
    .card { background: var(--card); border: 1px solid #30363d; border-radius: 8px; padding: 0.75rem 1rem; }
    .card h2 { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin: 0 0 0.5rem; }
    .val { font-size: 1.25rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .sub { font-size: 0.75rem; color: var(--muted); margin-top: 0.35rem; word-break: break-word; line-height: 1.35; }
    .ok { color: var(--ok); } .bad { color: var(--bad); }
    table.data { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    table.data th, table.data td { text-align: left; padding: 0.35rem 0.45rem; border-bottom: 1px solid #30363d; vertical-align: top; }
    table.data th { color: var(--muted); font-weight: 500; width: 38%; }
    #err { color: var(--bad); font-size: 0.85rem; margin-bottom: 1rem; display: none; }
    #meta { font-size: 0.72rem; color: var(--muted); margin-top: 1rem; }
    .ls { font-size: 0.85rem; line-height: 1.45; margin: 0 0 0.5rem; }
    .ls-detail { font-size: 0.78rem; color: var(--muted); margin: 0 0 0.75rem; }
    .chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.35rem; }
    .chip { font-size: 0.72rem; padding: 0.15rem 0.45rem; background: #21262d; border-radius: 4px; border: 1px solid #30363d; }
    details.raw { margin-top: 0.5rem; font-size: 0.75rem; color: var(--muted); }
    details.raw pre { white-space: pre-wrap; word-break: break-word; margin: 0.35rem 0 0; }
    .llm-bad { border-color: var(--bad) !important; background: #22191c; }
    .llm-warn { border-color: #9e6a03 !important; background: #1c1a12; }
    .llm-good { border-color: var(--ok) !important; background: #0d1f14; }
    #v_preflight_banner .sub { white-space: normal; word-break: break-word; }
    #v_llm_fail_alert { display:none; margin-bottom:0.75rem; padding:0.65rem 0.85rem; border-radius:8px; border:1px solid var(--bad); background:#2a1518; color:#f0d0d2; font-size:0.88rem; line-height:1.4; }
    #v_llm_fail_alert strong { color: #f85149; }
    details.dash-section { background: var(--card); border: 1px solid #30363d; border-radius: 8px; margin-bottom: 0.75rem; }
    details.dash-section > summary { list-style: none; cursor: pointer; padding: 0.65rem 0.85rem; user-select: none; display: flex; align-items: center; gap: 0.5rem; }
    details.dash-section > summary::-webkit-details-marker { display: none; }
    details.dash-section > summary::marker { content: ''; }
    details.dash-section > summary .dash-chev { color: var(--muted); font-size: 0.65rem; width: 1rem; flex-shrink: 0; }
    details.dash-section[open] > summary .dash-chev::before { content: '▼'; }
    details.dash-section:not([open]) > summary .dash-chev::before { content: '▶'; }
    details.dash-section > summary h2 { margin: 0; flex: 1; }
    details.dash-section .dash-inner { padding: 0 1rem 0.85rem; }
    details.dash-section#v_preflight_banner { border-width: 1px; }
    .dash-tools { margin: 0 0 0.65rem; font-size: 0.75rem; color: var(--muted); }
    .dash-tools button { font: inherit; font-size: 0.72rem; padding: 0.2rem 0.55rem; margin-right: 0.35rem; border-radius: 4px; border: 1px solid #30363d; background: #21262d; color: var(--text); cursor: pointer; }
    .dash-tools button:hover { border-color: var(--accent); color: var(--accent); }
    .scorecard-block { background: var(--card); border: 1px solid #30363d; border-radius: 8px; padding: 0.85rem 1rem; margin-bottom: 1rem; }
    table.trades-ledger { font-size: 0.78rem; }
    table.trades-ledger th { width: auto !important; white-space: nowrap; }
    table.trades-ledger .details-cell { max-width: 26rem; word-break: break-word; font-size: 0.76rem; color: #c9d1d9; }
    .res-won { color: var(--ok); font-weight: 600; text-transform: uppercase; }
    .res-lost { color: var(--bad); font-weight: 600; text-transform: uppercase; }
    .res-other { color: var(--muted); font-weight: 500; }
    table.activity-feed { font-size: 0.76rem; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; width: 100%; border-collapse: collapse; }
    table.activity-feed td { padding: 0.3rem 0.45rem; border-bottom: 1px solid #21262d; vertical-align: top; }
    table.activity-feed td.time { color: var(--muted); white-space: nowrap; width: 11.5rem; }
    table.activity-feed td.tag { color: var(--accent); width: 8rem; }
    table.activity-feed td.line { color: #c9d1d9; word-break: break-word; }
    .metric-flash { animation: metricFlash 0.75s ease-out; }
    @keyframes metricFlash { 0% { background: rgba(88,166,255,0.28); box-shadow: 0 0 0 1px rgba(88,166,255,0.4); } 100% { background: transparent; box-shadow: none; } }
    #v_iter.metric-flash, #v_rows.metric-flash { border-radius: 6px; padding: 0.15rem 0.35rem; margin: -0.15rem -0.35rem; }
    .digest-bar { font-size: 0.85rem; margin: 0 0 0.65rem; line-height: 1.45; }
    .digest-bar.pass { color: var(--ok); font-weight: 600; }
    .digest-bar.fail { color: var(--bad); font-weight: 600; }
    ul.digest-steps { list-style: none; margin: 0; padding: 0; font-size: 0.8rem; line-height: 1.4; }
    ul.digest-steps li { margin: 0 0 0.55rem; padding: 0.45rem 0.55rem; background: #0d1117; border-left: 3px solid #30363d; border-radius: 4px; }
    ul.digest-steps li .r { font-weight: 700; font-variant-numeric: tabular-nums; margin-right: 0.45rem; }
    ul.digest-steps li .r.ok { color: var(--ok); }
    ul.digest-steps li .r.bad { color: var(--bad); }
    ul.digest-steps li .r.neu { color: var(--muted); }
    .digest-why { font-size: 0.72rem; color: var(--muted); margin: 0.35rem 0 0; padding-left: 0.85rem; border-left: 2px solid #30363d; }
  </style>
  <script src="/text-scale.js"></script>
</head>
<body>
  <h1>Anna training — live</h1>
  <p class="lead">Refreshes every 4s. Grade-12 gate labels follow <strong>v1 governance</strong>: PASS = <em>qualified (provisional)</em> on the current ledger — not universal trust. Scorecard + ledger = rolling numbers.</p>
  <p class="dash-tools"><button type="button" id="btn_expand_all" title="Open all sections">Expand all</button><button type="button" id="btn_collapse_all" title="Close all collapsible sections">Collapse all</button></p>
  <div id="v_llm_fail_alert" role="alert"></div>
  <div id="v_ledger_alert" role="alert" style="display:none;margin:0 0 0.85rem;padding:0.65rem 0.85rem;border-radius:8px;border:1px solid #f85149;background:#3d1114;color:#f0f3f6;font-size:0.78rem;line-height:1.4"></div>
  <div id="err"></div>
  <section class="scorecard-block" style="border:1px solid #3fb95044" aria-labelledby="digest-h">
    <h2 id="digest-h" style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--ok);margin:0 0 0.45rem">Training run — where she is (last tick + Grade-12 bar)</h2>
    <p class="sub" id="v_digest_meta" style="margin:0 0 0.5rem;font-size:0.72rem">—</p>
    <p class="sub" id="v_digest_note" style="margin:0 0 0.45rem;font-size:0.7rem;color:var(--muted);line-height:1.35">—</p>
    <p class="digest-bar" id="v_digest_grade12">—</p>
    <p class="sub" id="v_digest_grade12_sub" style="margin:0 0 0.5rem;font-size:0.7rem;color:var(--muted);line-height:1.35">—</p>
    <div id="v_digest_why_wrap" style="display:none"></div>
    <ul class="digest-steps" id="v_digest_steps" aria-label="Last tick steps"></ul>
  </section>
  <details class="dash-section">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Optional — short log lines (no cycle spam)</h2></summary>
    <div class="dash-inner">
    <div style="overflow-x:auto"><table class="activity-feed" aria-label="Optional log tail"><tbody id="v_activity_body"></tbody></table></div>
    </div>
  </details>
  <section class="scorecard-block" aria-labelledby="scorecard-h">
    <h2 id="scorecard-h" style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);margin:0 0 0.65rem">Scorecard</h2>
    <p class="ls" id="v_ls_head" style="margin-top:0">—</p>
    <p class="sub" id="v_enroll" style="margin:0.35rem 0 0.75rem">—</p>
    <div class="grid">
      <div class="card" style="border:1px solid #30363d;margin:0"><h2>Supervisor ticks</h2><div class="val" id="v_iter">—</div><div class="sub" id="v_tick"></div></div>
      <div class="card" style="border:1px solid #30363d;margin:0"><h2>Grade-12 gates</h2><div class="val" id="v_gate">—</div><div class="sub" id="v_gdetail"></div></div>
      <div class="card" style="border:1px solid #30363d;margin:0"><h2>Paper trades (rows)</h2><div class="val" id="v_rows">—</div><div class="sub">Scored rows in <code>paper_trades.jsonl</code></div><div class="val" id="v_pnl" style="font-size:1rem;margin-top:0.35rem">—</div></div>
      <div class="card" style="border:1px solid #30363d;margin:0"><h2>Attempt log (JSONL lines)</h2><div class="val" id="v_attempts">—</div><div class="sub" id="v_attempts_hint" style="font-size:0.7rem">Total = lines in <code>paper_trade_attempts.jsonl</code>. Breakdown only counts known phase/status; rest shows as uncategorized or by_phase.</div><div class="sub" id="v_jack"></div></div>
    </div>
  </section>
  <section class="scorecard-block" aria-labelledby="trades-h" style="margin-top:0">
    <h2 id="trades-h" style="font-size:0.95rem;font-weight:600;margin:0 0 0.35rem;color:var(--text)">Paper trades — every row</h2>
    <p class="sub" style="margin:0 0 0.5rem">Newest first. Full UTC time, outcome, P&amp;L, symbol, side, timeframe, notes, source.</p>
    <div style="overflow-x:auto">
    <table class="data trades-ledger"><thead><tr>
      <th>Time (UTC)</th><th>Result</th><th>P&amp;L $</th><th>Symbol</th><th>Side</th><th>TF</th><th>Details</th><th>Src</th>
    </tr></thead><tbody id="tb"></tbody></table>
    </div>
  </section>
  <details class="dash-section llm-good" id="v_preflight_banner" style="display:none">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Preflight (data + LLM — same order as the daemon)</h2></summary>
    <div class="dash-inner">
    <p class="sub" style="font-size:0.72rem;color:var(--muted);margin:0 0 0.5rem">Red/warn here means a <strong>probe</strong> failed (feeds or Ollama), not a corrupt <code>state.json</code> file.</p>
    <p class="sub" id="v_data_pf">—</p>
    <p class="sub" id="v_llm_pf" style="margin-top:0.45rem">—</p>
    <p class="sub" id="v_pf_policy" style="margin-top:0.45rem;font-size:0.72rem;color:var(--muted)"></p>
    </div>
  </details>
  <details class="dash-section" style="border-color:#238636">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Governance — v1 PASS semantics (contract)</h2></summary>
    <div class="dash-inner">
    <p class="sub" style="font-size:0.72rem;color:var(--muted);margin:0 0 0.5rem">Machine-readable copy: <code>/api/v1/anna/training-dashboard</code> → <code>v1_governance_contract</code>.</p>
    <pre id="v_v1_gov" style="font-size:0.7rem;white-space:pre-wrap;word-break:break-word;margin:0;padding:0.65rem;background:#0d1117;border-radius:6px;border:1px solid #30363d;color:#c9d1d9">—</pre>
    </div>
  </details>
  <details class="dash-section" style="border-color:#484f58">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Housekeeping — tick vs paper vs attempts (semantics)</h2></summary>
    <div class="dash-inner">
    <p class="sub" id="v_sem1"></p>
    <p class="sub" id="v_sem2"></p>
    <p class="sub" id="v_sem3"></p>
    </div>
  </details>
  <details class="dash-section">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Grade-12 learning signal (detail)</h2></summary>
    <div class="dash-inner">
    <p class="ls-detail" id="v_ls_detail">—</p>
    </div>
  </details>
  <details class="dash-section" style="border-color:var(--accent)">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Last tick — Anna analysis (same stack as messaging Anna)</h2></summary>
    <div class="dash-inner">
    <p class="sub" id="v_snap_hint">From the last school harness save: full analyst fields — refreshed each daemon tick.</p>
    <div class="chips" id="v_steps"></div>
    <table class="data" id="v_analysis_tbl"><tbody id="v_analysis_body"></tbody></table>
    </div>
  </details>
  <details class="dash-section">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Last tick — Grade-12 tool drill (classroom)</h2></summary>
    <div class="dash-inner">
    <p class="sub">When deck focus is <code>numeric_paper_cohort</code>, there is no four-tool drill that tick — focus is the paper cohort gate, not a tool ID.</p>
    <table class="data" id="v_sp_tbl"><tbody id="v_sp_body"></tbody></table>
    </div>
  </details>
  <details class="dash-section">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Attempt log — recent lines</h2></summary>
    <div class="dash-inner">
    <table class="data"><thead><tr><th>UTC</th><th>Phase</th><th>Status</th><th>Request</th></tr></thead><tbody id="tb_att"></tbody></table>
    </div>
  </details>
  <details class="dash-section">
    <summary><span class="dash-chev" aria-hidden="true"></span><h2>Harness state (execution bridge)</h2></summary>
    <div class="dash-inner">
    <p class="sub" id="v_harness_line">—</p>
    <details class="raw"><summary>Raw JSON (debug)</summary><pre id="v_harness">—</pre></details>
    </div>
  </details>
  <p id="meta"></p>
  <script>
  const pollMs = 4000;
  function harnessLine(h) {
    if (!h || typeof h !== 'object') return '—';
    if (h.enabled === false) return String(h.reason || 'harness off');
    if (h.error) return 'error: ' + h.error;
    if (h.skipped) return 'stopped: ' + h.skipped + (h.request_id ? ' · request_id=' + String(h.request_id).slice(0,12) : '');
    if (h.paper_logged === true) return 'paper_logged · execution=' + String(h.execution_status||'') + ' · req=' + String(h.request_id||'').slice(0,12);
    if (h.request_id) return 'request_id=' + String(h.request_id).slice(0,12) + '… (see skipped/stopped above if no fill)';
    return '—';
  }
  function row(tbl, k, v) {
    var tr = document.createElement('tr');
    var th = document.createElement('th'); th.textContent = k;
    var td = document.createElement('td'); td.textContent = v == null || v === '' ? '—' : String(v);
    tr.appendChild(th); tr.appendChild(td); tbl.appendChild(tr);
  }
  async function tick() {
    const err = document.getElementById('err');
    try {
      const r = await fetch('/api/v1/anna/training-dashboard', { cache: 'no-store' });
      const j = await r.json();
      err.style.display = 'none';
      if (!j.ok) { err.textContent = (j.error || 'error') + ': ' + (j.detail || ''); err.style.display = 'block'; return; }
      (function ledgerAlert() {
        var el = document.getElementById('v_ledger_alert');
        if (!el) return;
        var ws = (j.paper_cohort && j.paper_cohort.warnings) || [];
        var vac = j.gates && j.gates.cohort_vacuous_all_wins_zero_pnl;
        if (!ws.length && !vac) { el.style.display = 'none'; el.innerHTML = ''; return; }
        el.style.display = 'block';
        var parts = [];
        ws.forEach(function(w) {
          if (!w || !w.message) return;
          parts.push('<strong>' + String(w.code || 'ledger') + '</strong>: ' + String(w.message) +
            (w.fix ? ' — <span style="opacity:0.95">' + String(w.fix) + '</span>' : ''));
        });
        if (vac && !ws.length) {
          parts.push('<strong>vacuous_cohort</strong>: Every decisive row is won with $0 P&amp;L — remove JACK_STUB_ALWAYS_WIN; drop legacy JACK_STUB_SIMULATE from .env; consider flush-runtime + Karpathy restart.');
        }
        el.innerHTML = parts.join('<br/>');
      })();
      var sem = j.semantics || {};
      document.getElementById('v_sem1').textContent = sem.loop_tick_means || '—';
      document.getElementById('v_sem2').textContent = sem.attempt_log_vs_tick || '—';
      document.getElementById('v_sem3').textContent = sem.paper_ledger_vs_tick || '—';
      (function fillV1Governance() {
        var pre = document.getElementById('v_v1_gov');
        if (!pre) return;
        var c = j.v1_governance_contract;
        pre.textContent = (c && typeof c === 'object') ? JSON.stringify(c, null, 2) : '—';
      })();
      (function preflightBanner() {
        var d = j.data_preflight || {};
        var l = j.llm_preflight || {};
        var pol = j.preflight_policy || {};
        function dataLine() {
          if (!d || typeof d !== 'object' || Object.keys(d).length === 0) {
            return { tier: 1, text: 'No saved data-preflight row yet — run the school daemon once so training state is updated.' };
          }
          if (d.skipped) return { tier: 1, text: 'Skipped (ANNA_SKIP_PREFLIGHT) — enforcement bypassed.' };
          if (d.ok) return { tier: 0, text: 'OK — Pyth stream + market_data.db (and optional Solana) passed this tick.' };
          var blockers = (d.blockers || []).join(', ');
          return { tier: 2, text: 'Blocked — ' + (blockers || 'unknown') + '. Fix feeds; see readiness in heartbeat JSONL or anna_training_dir.' };
        }
        function llmLine() {
          if (!l || typeof l !== 'object' || Object.keys(l).length === 0) {
            return { tier: 1, text: 'No LLM probe row yet — daemon has not finished a tick that saved llm_preflight.' };
          }
          if (l.skipped) return { tier: 0, text: 'Skipped (' + (l.reason || 'ANNA_USE_LLM off') + ').' };
          if (l.ok === true && l.model_present_in_tags !== false) {
            return { tier: 0, text: 'OK — ' + (l.ollama_model_configured || '') + ' present · ' + (l.base_url || '') };
          }
          if (l.ok === true && l.model_present_in_tags === false) {
            return { tier: 1, text: 'Ollama up but model ' + (l.ollama_model_configured || '') + ' not listed in /api/tags (ollama pull).' };
          }
          var err = (l.error != null && String(l.error) !== '') ? String(l.error) : 'probe not OK (check OLLAMA_BASE_URL / ollama serve)';
          return { tier: 2, text: 'Ollama probe failed — ' + err + (l.base_url ? ' · base ' + l.base_url : '') };
        }
        var dataPf = dataLine();
        var llmPf = llmLine();
        document.getElementById('v_data_pf').textContent = 'Data: ' + dataPf.text;
        document.getElementById('v_llm_pf').textContent = 'LLM: ' + llmPf.text;
        var worst = Math.max(dataPf.tier, llmPf.tier);
        var ban = document.getElementById('v_preflight_banner');
        ban.className = 'dash-section ' + (worst >= 2 ? 'llm-bad' : (worst >= 1 ? 'llm-warn' : 'llm-good'));
        ban.style.display = '';
        var alertEl = document.getElementById('v_llm_fail_alert');
        alertEl.style.borderColor = '';
        alertEl.style.background = '';
        alertEl.style.color = '';
        if (llmPf.tier >= 2) {
          alertEl.style.display = 'block';
          alertEl.innerHTML = '<strong>LLM probe failed</strong> — school still runs; fix Ollama or <code>OLLAMA_BASE_URL</code>. ' +
            llmPf.text.replace(/^Ollama probe failed — /, '');
        } else if (llmPf.tier >= 1 && l && !l.skipped) {
          alertEl.style.display = 'block';
          alertEl.style.borderColor = '#9e6a03';
          alertEl.style.background = '#1c1a12';
          alertEl.style.color = '#e3b341';
          alertEl.innerHTML = '<strong>LLM warning</strong> — ' + llmPf.text;
        } else {
          alertEl.style.display = 'none';
          alertEl.innerHTML = '';
        }
        document.getElementById('v_pf_policy').textContent = (pol.llm_probe_never_blocks_school !== false)
          ? 'Policy: the LLM line is informational — the loop does not skip school on Ollama errors. Fix OLLAMA_BASE_URL and model for real generations.'
          : 'Policy: see preflight_policy in JSON.';
      })();
      (function fillDigest() {
        var d = j.training_run_digest || {};
        var meta = document.getElementById('v_digest_meta');
        var g = document.getElementById('v_digest_grade12');
        var whyWrap = document.getElementById('v_digest_why_wrap');
        var ul = document.getElementById('v_digest_steps');
        if (!meta || !g || !ul || !whyWrap) return;
        meta.textContent =
          (d.last_iteration != null ? 'Last harness save · iteration ' + d.last_iteration : '—') +
          (d.last_tick_at ? ' · ' + d.last_tick_at : '');
        var noteEl = document.getElementById('v_digest_note');
        if (noteEl) noteEl.textContent = d.digest_note || '';
        var pass = d.grade12_pass === true;
        g.className = 'digest-bar ' + (pass ? 'pass' : 'fail');
        g.textContent = d.grade12_bar_title || (pass ? 'Grade-12 gate: QUALIFIED (provisional)' : 'Grade-12 gate: NOT QUALIFIED');
        var gsub = document.getElementById('v_digest_grade12_sub');
        if (gsub) gsub.textContent = d.grade12_bar_subtitle || '';
        while (whyWrap.firstChild) whyWrap.removeChild(whyWrap.firstChild);
        whyWrap.style.display = 'none';
        var whys = d.why_grade12_not_pass || [];
        if (!pass && whys.length) {
          whyWrap.style.display = 'block';
          var hw = document.createElement('p');
          hw.style.fontSize = '0.72rem';
          hw.style.color = 'var(--muted)';
          hw.style.margin = '0 0 0.35rem';
          var st = document.createElement('strong');
          st.textContent = 'Why NOT QUALIFIED';
          hw.appendChild(st);
          hw.appendChild(document.createTextNode(' (aggregate — tools + paper cohort, not one tick):'));
          whyWrap.appendChild(hw);
          whys.forEach(function(line) {
            var p = document.createElement('p');
            p.className = 'digest-why';
            p.textContent = line;
            whyWrap.appendChild(p);
          });
        }
        ul.innerHTML = '';
        (d.steps || []).forEach(function(s) {
          var li = document.createElement('li');
          var res = String(s.result || '—').toUpperCase();
          var rspan = document.createElement('span');
          var rc = 'neu';
          if (res === 'OK' || res === 'YES') rc = 'ok';
          else if (res === 'WON') rc = 'ok';
          else if (res === 'LOST') rc = 'bad';
          else if (res === 'FAIL' || res === 'NO' || res === 'BLOCKED') rc = 'bad';
          rspan.className = 'r ' + rc;
          rspan.textContent = res + ' ';
          li.appendChild(rspan);
          var strong = document.createElement('strong');
          strong.textContent = (s.step || '') + ' — ';
          li.appendChild(strong);
          li.appendChild(document.createTextNode(s.detail || ''));
          ul.appendChild(li);
        });
      })();
      (function fillActivity() {
        var body = document.getElementById('v_activity_body');
        if (!body) return;
        body.innerHTML = '';
        var feed = j.activity_feed || [];
        if (!feed.length) {
          var tr0 = document.createElement('tr');
          var td0 = document.createElement('td');
          td0.colSpan = 3;
          td0.className = 'sub';
          td0.style.fontFamily = 'inherit';
          td0.textContent = 'No optional log lines — school daemon will add tail events here (cycle lines are hidden).';
          tr0.appendChild(td0);
          body.appendChild(tr0);
          return;
        }
        feed.forEach(function(row) {
          var tr = document.createElement('tr');
          var t0 = document.createElement('td'); t0.className = 'time'; t0.textContent = row.ts_utc || '—';
          var t1 = document.createElement('td'); t1.className = 'tag'; t1.textContent = row.tag || '—';
          var t2 = document.createElement('td'); t2.className = 'line'; t2.textContent = row.line || '—';
          tr.appendChild(t0); tr.appendChild(t1); tr.appendChild(t2);
          body.appendChild(tr);
        });
      })();
      var ls = j.learning_signal || {};
      var hl = ls.headline || '—';
      if (hl.length > 200) hl = hl.slice(0, 197) + '…';
      document.getElementById('v_ls_head').textContent = hl;
      document.getElementById('v_ls_detail').textContent = ls.detail || '';
      var enr = j.enrollment || {};
      document.getElementById('v_enroll').textContent =
        'Curriculum: ' + (enr.curriculum_id || '—') + ' · Method: ' + (enr.training_method_id || '—') +
        (j.skills_deck_focus ? ' · Deck focus: ' + j.skills_deck_focus : '');
      var as = j.analysis_snapshot || {};
      var ab = document.getElementById('v_analysis_body');
      ab.innerHTML = '';
      document.getElementById('v_snap_hint').style.display = Object.keys(as).length ? 'block' : 'none';
      var stel = document.getElementById('v_steps');
      stel.innerHTML = '';
      if (as.answer_source) {
        var c0 = document.createElement('span');
        c0.className = 'chip';
        c0.textContent = 'answer_source: ' + as.answer_source;
        stel.appendChild(c0);
      }
      (as.pipeline_steps || []).forEach(function(s) {
        var c = document.createElement('span');
        c.className = 'chip';
        c.textContent = s;
        stel.appendChild(c);
      });
      if (Object.keys(as).length) {
        row(ab, 'Generated (UTC)', as.generated_at || '—');
        row(ab, 'Headline', as.interpretation_headline);
        row(ab, 'Summary', as.interpretation_summary);
        row(ab, 'Concepts used', (as.concepts_used || []).join(', ') || '—');
        row(ab, 'Policy guardrail mode', as.policy_guardrail_mode || '—');
        row(ab, 'Policy alignment', as.policy_alignment || '—');
        row(ab, 'Strategy playbook applied', as.strategy_playbook_applied != null ? String(as.strategy_playbook_applied) : '—');
        row(ab, 'Strategy concepts (detected)', (as.strategy_concepts_detected || []).join(', ') || '—');
        row(ab, 'Strategy explanation', as.strategy_explanation || '—');
        row(ab, 'Strategy risks', (as.strategy_risks || []).join(' · ') || '—');
        row(ab, 'Trading-core signal snapshot', as.trading_core_signal_snapshot || '—');
        row(ab, 'Math engine (snapshot)', as.math_engine_snapshot || '—');
        row(ab, 'Risk level', as.risk_level);
        row(ab, 'Risk factors', (as.risk_factors || []).join(' · ') || '—');
        row(ab, 'Suggested intent', as.suggested_intent);
        row(ab, 'Suggested rationale', as.suggested_rationale || '—');
        var mps = (as.market_price != null ? as.market_price : '—') + ' / ' + (as.market_spread != null ? as.market_spread : '—');
        if (as.market_price == null && as.market_spread == null) {
          mps += ' — (no price in snapshot: market snapshot / DB tasks may be empty; see Notes)';
        }
        row(ab, 'Market price / spread', mps);
        row(ab, 'Regime', as.regime || '—');
        row(ab, 'Signals', (as.interpretation_signals || []).join(', ') || '—');
        row(ab, 'Cumulative log entries (school)', as.cumulative_log_entries != null ? String(as.cumulative_log_entries) : '—');
        row(ab, 'Notes (tail)', (as.analysis_notes_tail || []).join(' | ') || '—');
      } else {
        var tr = document.createElement('tr');
        var td = document.createElement('td');
        td.colSpan = 2;
        td.textContent = 'No analysis snapshot yet — school harness must persist analysis_snapshot on each tick.';
        tr.appendChild(td);
        ab.appendChild(tr);
      }
      var sp = j.skill_practice_last || {};
      var sb = document.getElementById('v_sp_body');
      sb.innerHTML = '';
      row(sb, 'Drill ran this tick', sp.ran ? 'yes' : 'no');
      row(sb, 'Deck focus (snapshot)', sp.current_focus || j.skills_deck_focus || '—');
      var noteText = sp.note || '—';
      if (sp.ran) noteText = '(n/a — tool drill ran this tick)';
      row(sb, 'Why no tool drill / note', noteText);
      row(sb, 'Skill id', sp.skill_id || '—');
      row(sb, 'Passed', sp.passed != null ? (sp.passed ? 'yes' : 'no') : '—');
      row(sb, 'Summary', sp.summary || '—');
      row(sb, 'Practice kind', sp.practice_kind || '—');
      var det = sp.detail;
      if (det != null && typeof det === 'object') {
        row(sb, 'Detail', JSON.stringify(det));
      } else {
        row(sb, 'Detail', det != null && det !== '' ? String(det) : '—');
      }
      var iterEl = document.getElementById('v_iter');
      var newIter = j.loop.karpathy_loop_iteration;
      iterEl.textContent = newIter ?? '—';
      if (window._dashPrevIter != null && newIter != null && Number(newIter) !== Number(window._dashPrevIter)) {
        iterEl.classList.add('metric-flash');
        setTimeout(function() { iterEl.classList.remove('metric-flash'); }, 850);
      }
      window._dashPrevIter = newIter;
      document.getElementById('v_tick').textContent = j.loop.karpathy_loop_last_tick_utc ? 'last tick ' + j.loop.karpathy_loop_last_tick_utc : '';
      const gp = j.gates.pass;
      const ge = document.getElementById('v_gate');
      ge.textContent = (j.gates.pass_label_v1 != null && j.gates.pass_label_v1 !== '') ? j.gates.pass_label_v1 : (gp ? 'PASS' : 'NOT PASS');
      ge.className = 'val ' + (gp ? 'ok' : 'bad');
      document.getElementById('v_gdetail').textContent = 'decisive ' + (j.gates.decisive_trades||0) + '/' + (j.gates.min_decisive_trades||'—') +
        (j.gates.win_rate != null ? ' · WR ' + (100*j.gates.win_rate).toFixed(0) + '%' : '');
      var rowEl = document.getElementById('v_rows');
      var newRows = j.paper_cohort.row_count;
      rowEl.textContent = newRows;
      if (window._dashPrevRows != null && newRows != null && Number(newRows) !== Number(window._dashPrevRows)) {
        rowEl.classList.add('metric-flash');
        setTimeout(function() { rowEl.classList.remove('metric-flash'); }, 850);
      }
      window._dashPrevRows = newRows;
      document.getElementById('v_pnl').textContent = 'W'+j.paper_cohort.wins+' L'+j.paper_cohort.losses+' · $'+Number(j.paper_cohort.total_pnl_usd||0).toFixed(2);
      document.getElementById('v_attempts').textContent = j.attempts.total_events;
      var aj = j.attempts || {};
      var pct = aj.phase_status_counts || {};
      var phaseKeys = Object.keys(pct).sort();
      var phaseStr = phaseKeys.length ? phaseKeys.map(function(k) { return k + '=' + pct[k]; }).join(' · ') : '';
      document.getElementById('v_jack').textContent =
        'uncategorized ' + (aj.uncategorized != null ? aj.uncategorized : '—') +
        ' · Jack started ' + (aj.jack_delegate_started||0) +
        ' · ok+paper ' + (aj.jack_ok_with_paper||0) +
        ' · ok no paper ' + (aj.jack_ok_no_paper||0) +
        ' · manual log ' + (aj.paper_manual_recorded||0) +
        ' · exec blocked ' + (aj.execution_blocked != null ? aj.execution_blocked : 0) +
        ' · Jack failed ' + (aj.jack_delegate_failed||0) +
        (phaseStr ? ' · by_phase: ' + phaseStr : '');
      document.getElementById('v_harness_line').textContent = harnessLine(j.paper_harness_last);
      document.getElementById('v_harness').textContent = JSON.stringify(j.paper_harness_last || {}, null, 2);
      const tb = document.getElementById('tb');
      tb.innerHTML = '';
      var tradesList = j.recent_trades || [];
      if (!tradesList.length) {
        var trEmpty = document.createElement('tr');
        var tdEmpty = document.createElement('td');
        tdEmpty.colSpan = 8;
        tdEmpty.className = 'sub';
        tdEmpty.textContent = 'No paper trades yet — rows appear when a paper trade is logged to paper_trades.jsonl.';
        trEmpty.appendChild(tdEmpty);
        tb.appendChild(trEmpty);
      } else tradesList.forEach(function(row) {
        const tr = document.createElement('tr');
        var res = String(row.result || '').toLowerCase();
        var ts = row.ts_utc != null ? String(row.ts_utc) : '—';
        var pnlStr = row.pnl_usd != null ? Number(row.pnl_usd).toFixed(2) : '—';
        var sym = row.symbol != null && row.symbol !== '' ? String(row.symbol) : '—';
        var side = row.side != null && row.side !== '' ? String(row.side) : '—';
        var tf = row.timeframe != null && row.timeframe !== '' ? String(row.timeframe) : '—';
        var notes = row.notes != null ? String(row.notes) : '—';
        if (notes.length > 500) notes = notes.slice(0, 500) + '…';
        var src = row.source != null && row.source !== '' ? String(row.source) : '—';
        function addTd(text, opts) {
          var td = document.createElement('td');
          td.textContent = text;
          if (opts && opts.className) td.className = opts.className;
          if (opts && opts.title) td.title = opts.title;
          tr.appendChild(td);
        }
        addTd(ts);
        var tdRes = document.createElement('td');
        tdRes.textContent = row.result != null && row.result !== '' ? String(row.result) : '—';
        tdRes.className = res === 'won' ? 'res-won' : (res === 'lost' ? 'res-lost' : 'res-other');
        tr.appendChild(tdRes);
        var tdPnl = document.createElement('td');
        tdPnl.textContent = pnlStr;
        tdPnl.style.fontVariantNumeric = 'tabular-nums';
        if (pnlStr !== '—' && !isNaN(Number(pnlStr))) tdPnl.className = Number(pnlStr) >= 0 ? 'ok' : 'bad';
        tr.appendChild(tdPnl);
        addTd(sym);
        addTd(side);
        addTd(tf);
        var tdDet = document.createElement('td');
        tdDet.className = 'details-cell';
        tdDet.textContent = notes;
        tr.appendChild(tdDet);
        addTd(src);
        tb.appendChild(tr);
      });
      var tba = document.getElementById('tb_att');
      tba.innerHTML = '';
      (j.attempt_events_recent || []).forEach(function(ev) {
        var tr = document.createElement('tr');
        ['ts_utc','phase','status','request_id'].forEach(function(k) {
          var td = document.createElement('td');
          td.textContent = ev[k] != null && ev[k] !== '' ? String(ev[k]) : '—';
          tr.appendChild(td);
        });
        tba.appendChild(tr);
      });
      document.getElementById('meta').textContent = 'Updated ' + (j.at_utc || '') + ' · trace ' + (j.trace_id||'').slice(0,8);
    } catch (e) {
      err.textContent = String(e);
      err.style.display = 'block';
    }
  }
  tick();
  setInterval(tick, pollMs);
  document.getElementById('btn_expand_all').addEventListener('click', function() {
    document.querySelectorAll('details.dash-section').forEach(function(el) { el.open = true; });
  });
  document.getElementById('btn_collapse_all').addEventListener('click', function() {
    document.querySelectorAll('details.dash-section').forEach(function(el) { el.open = false; });
  });
  </script>
</body>
</html>
"""


def _kitchen_blackbox_get_authorized(handler: BaseHTTPRequestHandler) -> bool:
    exp = (os.environ.get("KITCHEN_BLACKBOX_OPERATOR_TOKEN") or "").strip()
    if not exp:
        return True
    auth = (handler.headers.get("Authorization") or "").strip()
    tok = auth[7:].strip() if auth.startswith("Bearer ") else ""
    return hmac.compare_digest(tok, exp)


def _kitchen_blackbox_post_authorized(handler: BaseHTTPRequestHandler) -> bool:
    exp = (os.environ.get("KITCHEN_BLACKBOX_OPERATOR_TOKEN") or "").strip()
    if not exp:
        return False
    auth = (handler.headers.get("Authorization") or "").strip()
    tok = auth[7:].strip() if auth.startswith("Bearer ") else ""
    return hmac.compare_digest(tok, exp)


class Handler(BaseHTTPRequestHandler):
    def _read_json_body(self) -> dict[str, Any]:
        ln = int(self.headers.get("Content-Length") or 0)
        if ln <= 0:
            return {}
        raw = self.rfile.read(ln)
        try:
            out = json.loads(raw.decode("utf-8"))
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _json(
        self,
        code: int,
        body: dict[str, Any] | list[Any],
        *,
        no_cache: bool = False,
    ) -> None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        enc = (self.headers.get("Accept-Encoding") or "").lower()
        use_gzip = len(payload) > 2048 and "gzip" in enc
        if use_gzip:
            payload = gzip.compress(payload, compresslevel=6)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        if no_cache:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _html(self, code: int, body: str, *, no_cache: bool = False) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if no_cache:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _bytes(
        self,
        code: int,
        data: bytes,
        *,
        content_type: str,
        filename: str | None = None,
        no_cache: bool = True,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        if no_cache:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/v1/runtime/status":
            runtime, _ = build_status()
            self._json(200, runtime)
            return
        if path == "/api/v1/blackbox/policy":
            if not _kitchen_blackbox_get_authorized(self):
                self._json(401, {"ok": False, "error": "unauthorized"}, no_cache=True)
                return
            from renaissance_v4.blackbox_policy_control_plane import get_policy_observability_payload

            self._json(200, get_policy_observability_payload(_REPO_ROOT), no_cache=True)
            return
        if path == "/api/v1/agents/status":
            _, agents = build_status()
            self._json(200, agents)
            return
        if path == "/api/v1/market/pyth/status":
            self._json(200, build_pyth_status())
            return
        if path == "/api/v1/market/pyth/recent":
            recent = load_json(PYTH_RECENT_FILE)
            data = recent if isinstance(recent, dict) else {"items": []}
            q = parse_qs(parsed.query or "")
            limit_raw = (q.get("limit") or ["40"])[0]
            try:
                limit = max(1, min(200, int(limit_raw)))
            except ValueError:
                limit = 40
            items = data.get("items") if isinstance(data.get("items"), list) else []
            self._json(200, {"items": items[-limit:], "trace_id": str(uuid.uuid4())})
            return
        if path == "/api/v1/market/binance/ping":
            self._json(200, build_binance_ping(), no_cache=True)
            return
        if path == "/api/v1/market/ingest-health":
            try:
                from modules.anna_training.dashboard_bundle import _market_db_path
                from modules.anna_training.ingest_health import compute_ingest_health

                mp = _market_db_path()
                if mp is None or not mp.is_file():
                    self._json(
                        200,
                        {
                            "schema": "ingest_health_v1",
                            "healthy": False,
                            "state": "critical",
                            "operator_alert_code": "TAPE_STALLED",
                            "message": "market database path unavailable",
                            "ui_trust_tape_data": False,
                        },
                        no_cache=True,
                    )
                else:
                    self._json(200, compute_ingest_health(market_db_path=mp), no_cache=True)
            except Exception as e:
                self._json(
                    500,
                    {"schema": "ingest_health_v1", "healthy": False, "error": str(e)[:400]},
                    no_cache=True,
                )
            return
        if path == "/api/v1/anna/summary":
            self._json(200, build_anna_summary())
            return
        if path == "/api/v1/anna/training-dashboard":
            self._json(200, build_anna_training_dashboard(), no_cache=True)
            return
        if path == "/api/v1/anna/decision-trace":
            q = parse_qs(parsed.query or "")
            self._json(200, build_anna_decision_trace_read(q), no_cache=True)
            return
        if path == "/api/v1/anna/market-event-view":
            q = parse_qs(parsed.query or "")
            self._json(200, build_anna_market_event_view(q), no_cache=True)
            return
        if path == "/api/v1/anna/strategies/catalog":
            self._json(200, build_anna_strategy_catalog(), no_cache=True)
            return
        if path == "/api/v1/anna/evaluation-summary":
            q = parse_qs(parsed.query or "")
            self._json(200, build_anna_evaluation_summary(q), no_cache=True)
            return
        if path == "/api/v1/anna/operator-dashboard":
            q = parse_qs(parsed.query or "")
            self._json(200, build_anna_operator_dashboard(q), no_cache=True)
            return
        if path in ("/anna/event-dashboard", "/anna/event-dashboard/"):
            ev = _REPO_ROOT / "UIUX.Web" / "event_market_view.html"
            if ev.is_file():
                self._html(200, ev.read_text(encoding="utf-8"), no_cache=True)
                return
        if path in ("/anna/event-view-extended", "/anna/event-view-extended/"):
            ev = _REPO_ROOT / "UIUX.Web" / "event_market_view.html"
            if ev.is_file():
                self._html(200, ev.read_text(encoding="utf-8"), no_cache=True)
                return
        if path in ("/anna/event-view", "/anna/event-view/"):
            ev = _REPO_ROOT / "UIUX.Web" / "event_market_view.html"
            if ev.is_file():
                self._html(200, ev.read_text(encoding="utf-8"), no_cache=True)
                return
        if path in ("/anna/evaluation", "/anna/evaluation/"):
            ev = _REPO_ROOT / "UIUX.Web" / "evaluation_view.html"
            if ev.is_file():
                self._html(200, ev.read_text(encoding="utf-8"), no_cache=True)
                return
        if path in ("/anna/training", "/anna/training/"):
            self._html(200, TRAINING_DASHBOARD_HTML, no_cache=True)
            return
        if path in ("/anna/sequential-learning", "/anna/sequential-learning/"):
            sl = _REPO_ROOT / "UIUX.Web" / "sequential_learning_control.html"
            if sl.is_file():
                self._html(200, sl.read_text(encoding="utf-8"), no_cache=True)
                return
        if path in ("/dashboard", "/dashboard/", "/dashboard.html"):
            dash = _REPO_ROOT / "UIUX.Web" / "dashboard.html"
            if dash.is_file():
                self._html(200, dash.read_text(encoding="utf-8"), no_cache=True)
                return
        if path in ("/baseline-trades", "/baseline-trades/", "/baseline-trades.html"):
            bt = _REPO_ROOT / "UIUX.Web" / "baseline_trades.html"
            if bt.is_file():
                self._html(200, bt.read_text(encoding="utf-8"), no_cache=True)
                return
        if path in (
            "/baseline-chain-validate",
            "/baseline-chain-validate/",
            "/baseline-chain-validate.html",
        ):
            bcv = _REPO_ROOT / "UIUX.Web" / "baseline_chain_validate.html"
            if bcv.is_file():
                self._html(200, bcv.read_text(encoding="utf-8"), no_cache=True)
                return
        if path in ("/intelligence-method", "/intelligence-method/", "/intelligence-method.html"):
            im = _REPO_ROOT / "UIUX.Web" / "intelligence-method.html"
            if im.is_file():
                self._html(200, im.read_text(encoding="utf-8"), no_cache=True)
                return
        if path == "/api/v1/system/status":
            self._json(200, build_system_status())
            return
        if path == "/api/v1/wallet/status":
            if build_wallet_status_payload is None:
                self._json(
                    500,
                    {
                        "schema": "blackbox_wallet_status_v1",
                        "wallet_connected": False,
                        "error": "wallet_module_import_failed",
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            try:
                payload = build_wallet_status_payload()
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "blackbox_wallet_status_v1",
                        "wallet_connected": False,
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            self._json(200, payload, no_cache=True)
            return
        if path == "/api/v1/sequential-learning/control/status":
            try:
                from modules.anna_training.sequential_engine.ui_control import build_operator_status

                payload = build_operator_status()
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "ok": False,
                        "reason_code": "SEQUENTIAL_STATUS_EXCEPTION",
                        "detail": str(e),
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            payload = dict(payload)
            payload["ok"] = True
            payload["trace_id"] = str(uuid.uuid4())
            self._json(200, payload, no_cache=True)
            return
        if path == "/api/v1/paper-capital/summary":
            try:
                from modules.anna_training.paper_capital import build_paper_capital_summary
                from modules.anna_training.store import load_state

                body = build_paper_capital_summary(training_state=load_state())
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"ok": False, "schema": "paper_capital_summary_v1", "error": str(e)[:500]},
                    no_cache=True,
                )
                return
            self._json(200, body, no_cache=True)
            return
        if path == "/api/v1/dashboard/bundle":
            try:
                from modules.anna_training.dashboard_bundle import build_dashboard_bundle

                q = parse_qs(parsed.query or "")
                raw = (q.get("max_events") or ["24"])[0]
                try:
                    max_ev = max(4, min(48, int(raw)))
                except ValueError:
                    max_ev = 24
                body = build_dashboard_bundle(max_events=max_ev)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "blackbox_dashboard_bundle_v1",
                        "ok": False,
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            self._json(200, body, no_cache=True)
            return
        if path == "/api/v1/dashboard/baseline-trades-report":
            try:
                from modules.anna_training.dashboard_bundle import build_baseline_trades_report

                q = parse_qs(parsed.query or "")
                from_u = (q.get("from_utc") or [""])[0].strip() or None
                to_u = (q.get("to_utc") or [""])[0].strip() or None
                raw_lim = (q.get("limit") or ["50"])[0]
                try:
                    lim = max(1, min(500, int(raw_lim)))
                except ValueError:
                    lim = 50
                scope = (q.get("scope") or ["trade"])[0].strip().lower()
                if scope not in ("all", "trade", "no_trade"):
                    scope = "trade"
                tb = (q.get("time_basis") or ["entry"])[0].strip().lower()
                if tb not in ("entry", "exit"):
                    tb = "entry"
                body = build_baseline_trades_report(
                    from_utc_iso=from_u,
                    to_utc_iso=to_u,
                    limit=lim,
                    scope=scope,
                    time_basis=tb,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "ok": False,
                        "schema": "blackbox_baseline_trades_report_v7",
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            self._json(200, body, no_cache=True)
            return
        if path == "/api/v1/dashboard/policy-evaluation-forensic":
            try:
                from modules.anna_training.dashboard_bundle import build_policy_evaluation_forensic_v1

                q = parse_qs(parsed.query or "")
                mid = (q.get("market_event_id") or [""])[0].strip()
                if not mid:
                    self._json(
                        400,
                        {
                            "schema": "policy_evaluation_forensic_v1",
                            "ok": False,
                            "error": "market_event_id query parameter required",
                        },
                        no_cache=True,
                    )
                    return
                body = build_policy_evaluation_forensic_v1(market_event_id=mid)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "policy_evaluation_forensic_v1",
                        "ok": False,
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            self._json(200, body, no_cache=True)
            return
        if path == "/api/v1/dashboard/baseline-active-position":
            try:
                from modules.anna_training.dashboard_bundle import build_baseline_active_position_snapshot

                body = build_baseline_active_position_snapshot()
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "ok": False,
                        "schema": "blackbox_baseline_active_position_v1",
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            self._json(200, body, no_cache=True)
            return
        if path == "/api/v1/dashboard/baseline-chain-validate":
            try:
                from modules.anna_training.baseline_chain_validate import validate_range

                q = parse_qs(parsed.query or "")
                mode = (q.get("mode") or ["single"])[0].strip().lower() or "single"
                policy_slot = (q.get("policy_slot") or ["jup_v3"])[0].strip() or "jup_v3"
                candle = (q.get("candle_open_utc") or q.get("candle_open") or [""])[0].strip() or None
                last_n_raw = (q.get("last_n") or ["12"])[0]
                try:
                    last_n = int(last_n_raw)
                except ValueError:
                    last_n = 12
                from_u = (q.get("from_utc") or q.get("from") or [""])[0].strip() or None
                to_u = (q.get("to_utc") or q.get("to") or [""])[0].strip() or None
                body = validate_range(
                    mode=mode,
                    policy_slot=policy_slot,
                    candle_open_utc_iso=candle,
                    last_n=last_n,
                    from_utc_iso=from_u,
                    to_utc_iso=to_u,
                )
            except ValueError as e:
                self._json(
                    400,
                    {
                        "schema": "baseline_chain_validate_v2",
                        "ok": False,
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "baseline_chain_validate_v2",
                        "ok": False,
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            self._json(200, body, no_cache=True)
            return
        if path == "/api/v1/context-engine/status":
            if build_context_engine_status is None or record_api_probe is None:
                self._json(
                    200,
                    {
                        "status": "error",
                        "reason_code": "CTX-ENGINE-IMPORT-FAIL",
                        "last_heartbeat_at": None,
                        "freshness_seconds": None,
                        "last_event_kind": None,
                        "record_count_hint": None,
                        "storage_path": None,
                        "trace_id": str(uuid.uuid4()),
                    },
                )
                return
            try:
                record_api_probe(ROOT)
                body = dict(build_context_engine_status(ROOT))
                body["trace_id"] = str(uuid.uuid4())
                self._json(200, body)
            except Exception as e:  # noqa: BLE001 — fail-closed surface for API
                self._json(
                    200,
                    {
                        "status": "error",
                        "reason_code": "CTX-STATUS-EXCEPTION",
                        "last_heartbeat_at": None,
                        "freshness_seconds": None,
                        "last_event_kind": None,
                        "record_count_hint": None,
                        "storage_path": None,
                        "detail": str(e),
                        "trace_id": str(uuid.uuid4()),
                    },
                )
            return
        if path == "/api/v1/renaissance/baseline":
            try:
                from renaissance_v4.execution_targets import normalize_execution_target
                from renaissance_v4.ui_api import build_baseline_payload

                q = parse_qs(parsed.query or "")
                et_raw = (q.get("execution_target") or ["jupiter"])[0].strip()
                et = normalize_execution_target(et_raw)
                body = build_baseline_payload(_REPO_ROOT, execution_target=et)
                body["trace_id"] = str(uuid.uuid4())
                self._json(200, body, no_cache=True)
            except ValueError as e:
                self._json(
                    400,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": "invalid_execution_target",
                        "detail": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/intake-candidates":
            q = parse_qs(parsed.query or "")
            et_raw = (q.get("execution_target") or [""])[0].strip()
            inc_arch_raw = (q.get("include_archived") or ["0"])[0].strip().lower()
            include_archived = inc_arch_raw in ("1", "true", "yes")
            collapse_raw = (q.get("collapse_duplicates") or ["1"])[0].strip().lower()
            collapse_duplicates = collapse_raw not in ("0", "false", "no")
            trace_id = str(uuid.uuid4())
            try:
                from renaissance_v4.execution_targets import normalize_execution_target
                from renaissance_v4.policy_intake.candidates_registry import list_intake_candidates

                et: str | None = None
                if et_raw:
                    et = normalize_execution_target(et_raw)
                rows = list_intake_candidates(
                    _REPO_ROOT,
                    execution_target=et,
                    include_archived=include_archived,
                    collapse_duplicate_policy_ids=collapse_duplicates,
                )
                self._json(
                    200,
                    {
                        "schema": "renaissance_v4_ui_intake_candidates_v1",
                        "candidates": rows,
                        "execution_target_filter": et,
                        "include_archived": include_archived,
                        "collapse_duplicates": collapse_duplicates,
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            except ValueError as e:
                self._json(
                    400,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": "invalid_execution_target",
                        "detail": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/kitchen-runtime-assignment":
            trace_id = str(uuid.uuid4())
            try:
                from renaissance_v4.execution_targets import normalize_execution_target
                from renaissance_v4.kitchen_policy_registry import load_registry
                from renaissance_v4.kitchen_runtime_assignment import (
                    MECHANICAL_CANDIDATE_POLICY_ID,
                    approved_mechanical_by_target,
                    build_kitchen_runtime_read_payload,
                    read_store,
                )

                q = parse_qs(parsed.query or "")
                et_raw = (q.get("execution_target") or [""])[0].strip()
                if et_raw:
                    et = normalize_execution_target(et_raw)
                    payload = build_kitchen_runtime_read_payload(_REPO_ROOT, et)
                    payload["trace_id"] = trace_id
                    self._json(
                        200,
                        payload,
                        no_cache=True,
                    )
                else:
                    st = read_store(_REPO_ROOT)
                    reg = load_registry(_REPO_ROOT)
                    self._json(
                        200,
                        {
                            "schema": "kitchen_runtime_assignment_store_read_v2",
                            "store": st,
                            "mechanical_candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
                            "approved_slots_by_target": {
                                k: v["approved_runtime_slot_id"]
                                for k, v in approved_mechanical_by_target(_REPO_ROOT).items()
                            },
                            "policy_registry": {
                                "schema": reg.get("schema"),
                                "runtime_policies": reg.get("runtime_policies"),
                            },
                            "note": "Per-target runtime truth and drift: GET with ?execution_target=jupiter|blackbox (DV-074).",
                            "trace_id": trace_id,
                        },
                        no_cache=True,
                    )
            except ValueError as e:
                self._json(
                    400,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": "invalid_execution_target",
                        "detail": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/kitchen-policy-ledger":
            trace_id = str(uuid.uuid4())
            try:
                from renaissance_v4.execution_targets import normalize_execution_target
                from renaissance_v4.kitchen_policy_ledger import ledger_entries_for_target

                q = parse_qs(parsed.query or "")
                et_raw = (q.get("execution_target") or [""])[0].strip()
                lim_raw = (q.get("limit") or ["50"])[0].strip()
                try:
                    limit = max(1, min(200, int(lim_raw)))
                except ValueError:
                    limit = 50
                if not et_raw:
                    self._json(
                        400,
                        {
                            "schema": "renaissance_v4_ui_error_v1",
                            "error": "missing_execution_target",
                            "detail": "Query execution_target=jupiter|blackbox is required",
                            "trace_id": trace_id,
                        },
                        no_cache=True,
                    )
                    return
                et = normalize_execution_target(et_raw)
                entries = ledger_entries_for_target(_REPO_ROOT, et, limit=limit)
                self._json(
                    200,
                    {
                        "schema": "kitchen_policy_assignment_ledger_read_v1",
                        "execution_target": et,
                        "entries": entries,
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            except ValueError as e:
                self._json(
                    400,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": "invalid_execution_target",
                        "detail": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/kitchen-jupiter-assignment":
            trace_id = str(uuid.uuid4())
            try:
                from renaissance_v4.kitchen_runtime_assignment import (
                    MECHANICAL_CANDIDATE_POLICY_ID,
                    approved_mechanical_by_target,
                    get_assignment,
                )

                jupiter_slot = approved_mechanical_by_target(_REPO_ROOT)["jupiter"]["approved_runtime_slot_id"]
                a = get_assignment(_REPO_ROOT, "jupiter")
                self._json(
                    200,
                    {
                        "schema": "kitchen_jupiter_assignment_read_v1",
                        "assignment": a,
                        "mechanical_candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
                        "jupiter_policy_slot": jupiter_slot,
                        "note": "Prefer GET /api/v1/renaissance/kitchen-runtime-assignment?execution_target=jupiter (DV-068).",
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
            return
        if path.startswith("/api/v1/renaissance/policy-intake/"):
            rest = path[len("/api/v1/renaissance/policy-intake/") :].strip().strip("/")
            if not rest or ".." in rest:
                self._json(400, {"ok": False, "error": "invalid_submission_id"}, no_cache=True)
                return
            parts_pi = [p for p in rest.split("/") if p]
            if len(parts_pi) == 2 and parts_pi[1] == "archive":
                self._json(
                    405,
                    {
                        "ok": False,
                        "error": "method_not_allowed",
                        "detail": "POST /api/v1/renaissance/policy-intake/{submission_id}/archive",
                    },
                    no_cache=True,
                )
                return
            sid = parts_pi[0] if parts_pi else ""
            if not sid or ".." in sid:
                self._json(400, {"ok": False, "error": "invalid_submission_id"}, no_cache=True)
                return
            try:
                from renaissance_v4.policy_intake.storage import read_json, submission_dir

                rep_path = submission_dir(_REPO_ROOT, sid) / "report" / "intake_report.json"
                rep = read_json(rep_path)
                if not isinstance(rep, dict):
                    self._json(404, {"ok": False, "error": "unknown_submission"}, no_cache=True)
                    return
                rep["trace_id"] = str(uuid.uuid4())
                self._json(200, rep, no_cache=True)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"ok": False, "error": str(e)[:500], "trace_id": str(uuid.uuid4())},
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/workbench":
            try:
                from renaissance_v4.ui_api import build_workbench_meta_payload

                body = build_workbench_meta_payload()
                body["trace_id"] = str(uuid.uuid4())
                self._json(200, body, no_cache=True)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/promotion-candidates":
            try:
                from renaissance_v4.research.sra_handoff import build_promotion_candidates_api_payload

                body = build_promotion_candidates_api_payload()
                body["trace_id"] = str(uuid.uuid4())
                self._json(200, body, no_cache=True)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/file":
            q = parse_qs(parsed.query or "")
            rel = (q.get("rel") or [""])[0].strip()
            try:
                from renaissance_v4.ui_api import resolve_safe_artifact_path

                p = resolve_safe_artifact_path(_REPO_ROOT, rel)
                if not p:
                    self._json(
                        404,
                        {"error": "not_found", "trace_id": str(uuid.uuid4())},
                        no_cache=True,
                    )
                    return
                raw = p.read_bytes()
                suf = p.suffix.lower()
                ct = "text/plain; charset=utf-8"
                if suf == ".md":
                    ct = "text/markdown; charset=utf-8"
                elif suf == ".json":
                    ct = "application/json; charset=utf-8"
                elif suf == ".csv":
                    ct = "text/csv; charset=utf-8"
                self._bytes(200, raw, content_type=ct, filename=p.name, no_cache=True)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/baseline/export":
            q = parse_qs(parsed.query or "")
            kind = (q.get("kind") or ["metrics"])[0].strip().lower()
            if kind not in ("trades", "metrics", "monte_carlo"):
                self._json(
                    400,
                    {"error": "invalid_kind", "allowed": ["trades", "metrics", "monte_carlo"]},
                    no_cache=True,
                )
                return
            try:
                from renaissance_v4.execution_targets import normalize_execution_target, paths_for_execution_target
                from renaissance_v4.ui_api import rv4_paths
                from renaissance_v4.ui_exports import export_baseline_csv

                et_raw = (q.get("execution_target") or ["jupiter"])[0].strip()
                et = normalize_execution_target(et_raw)
                p = rv4_paths(_REPO_ROOT)
                pt = paths_for_execution_target(_REPO_ROOT, et)
                csv_trades = (
                    "blackbox_baseline_v1_trades.csv"
                    if et == "blackbox"
                    else "baseline_v1_trades.csv"
                )
                csv_metrics = (
                    "blackbox_baseline_metrics.csv"
                    if et == "blackbox"
                    else "baseline_deterministic_metrics.csv"
                )
                csv_mc = (
                    "blackbox_baseline_monte_carlo.csv"
                    if et == "blackbox"
                    else "baseline_monte_carlo_summary.csv"
                )
                out = export_baseline_csv(
                    _REPO_ROOT,
                    kind,
                    reports_exp=p["experiments_dir"],
                    state_dir=p["state"],
                    baseline_trades_json=pt.get("baseline_trades_json"),
                    baseline_det_json=pt["baseline_det"],
                    baseline_mc_json=pt["baseline_mc"],
                    csv_trades_name=csv_trades,
                    csv_metrics_name=csv_metrics,
                    csv_mc_name=csv_mc,
                )
                if not out:
                    self._json(404, {"error": "artifact_missing", "trace_id": str(uuid.uuid4())}, no_cache=True)
                    return
                data, fn = out
                self._bytes(200, data, content_type="text/csv; charset=utf-8", filename=fn, no_cache=True)
            except ValueError as e:
                self._json(
                    400,
                    {"error": "invalid_execution_target", "detail": str(e)[:500], "trace_id": str(uuid.uuid4())},
                    no_cache=True,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"error": str(e)[:500], "trace_id": str(uuid.uuid4())},
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/experiments":
            try:
                from renaissance_v4.ui_api import build_experiments_list_payload

                body = build_experiments_list_payload(_REPO_ROOT)
                body["trace_id"] = str(uuid.uuid4())
                self._json(200, body, no_cache=True)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
            return
        if path.startswith("/api/v1/renaissance/experiments/"):
            suffix = path[len("/api/v1/renaissance/experiments/") :].strip("/")
            segs = [s for s in suffix.split("/") if s]
            if not segs:
                self._json(400, {"error": "missing_experiment_id", "trace_id": str(uuid.uuid4())}, no_cache=True)
                return
            if len(segs) >= 2 and segs[1] == "export":
                eid = segs[0]
                q = parse_qs(parsed.query or "")
                kind = (q.get("kind") or ["metrics"])[0].strip().lower()
                if kind not in ("trades", "metrics", "monte_carlo"):
                    self._json(
                        400,
                        {"error": "invalid_kind", "allowed": ["trades", "metrics", "monte_carlo"]},
                        no_cache=True,
                    )
                    return
                try:
                    from renaissance_v4.ui_api import get_candidate_trades_fallback, rv4_paths, validate_experiment_id
                    from renaissance_v4.ui_exports import export_experiment_csv

                    if not validate_experiment_id(eid):
                        self._json(400, {"error": "invalid_experiment_id"}, no_cache=True)
                        return
                    p = rv4_paths(_REPO_ROOT)
                    fb = get_candidate_trades_fallback(_REPO_ROOT, eid)
                    out = export_experiment_csv(
                        _REPO_ROOT,
                        eid,
                        kind,
                        state_dir=p["state"],
                        candidate_trades_fallback=fb,
                    )
                    if not out:
                        self._json(404, {"error": "artifact_missing", "trace_id": str(uuid.uuid4())}, no_cache=True)
                        return
                    data, fn = out
                    self._bytes(200, data, content_type="text/csv; charset=utf-8", filename=fn, no_cache=True)
                except Exception as e:  # noqa: BLE001
                    self._json(
                        500,
                        {
                            "schema": "renaissance_v4_ui_error_v1",
                            "error": str(e)[:500],
                            "trace_id": str(uuid.uuid4()),
                        },
                        no_cache=True,
                    )
                return
            if len(segs) != 1:
                self._json(404, {"error": "not_found", "path": path}, no_cache=True)
                return
            eid = segs[0]
            try:
                from renaissance_v4.ui_api import build_experiment_detail_payload

                body = build_experiment_detail_payload(_REPO_ROOT, eid)
                body["trace_id"] = str(uuid.uuid4())
                self._json(200, body, no_cache=True)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "renaissance_v4_ui_error_v1",
                        "error": str(e)[:500],
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
            return
        if path == "/api/v1/renaissance/jobs":
            try:
                from renaissance_v4.ui_jobs import load_queue

                q = load_queue(_REPO_ROOT)
                q["trace_id"] = str(uuid.uuid4())
                self._json(200, q, no_cache=True)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"error": str(e)[:500], "trace_id": str(uuid.uuid4())},
                    no_cache=True,
                )
            return
        if path in ("/renaissance", "/renaissance/"):
            self.send_response(302)
            self.send_header("Location", "/dashboard.html#/renaissance")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self._json(404, {"error": "not_found", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path_norm_early = (parsed.path or "").rstrip("/") or "/"
        if path_norm_early == "/api/v1/blackbox/active-policy":
            trace_id = str(uuid.uuid4())
            if not _kitchen_blackbox_post_authorized(self):
                exp = (os.environ.get("KITCHEN_BLACKBOX_OPERATOR_TOKEN") or "").strip()
                if not exp:
                    self._json(
                        503,
                        {
                            "ok": False,
                            "error": "operator_token_not_configured",
                            "detail": "Set KITCHEN_BLACKBOX_OPERATOR_TOKEN on the API host.",
                            "trace_id": trace_id,
                        },
                        no_cache=True,
                    )
                else:
                    self._json(401, {"ok": False, "error": "unauthorized", "trace_id": trace_id}, no_cache=True)
                return
            body = self._read_json_body() or {}
            pid = str(body.get("policy") or "").strip()
            from renaissance_v4.blackbox_policy_control_plane import set_active_policy

            ok, err = set_active_policy(_REPO_ROOT, pid)
            if not ok:
                self._json(
                    400,
                    {"ok": False, "error": err or "set_failed", "trace_id": trace_id},
                    no_cache=True,
                )
                return
            self._json(
                200,
                {
                    "ok": True,
                    "active_policy": pid,
                    "contract": "blackbox_active_policy_switch_v1",
                    "trace_id": trace_id,
                },
                no_cache=True,
            )
            return
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if (
            len(parts) == 6
            and parts[:4] == ["api", "v1", "renaissance", "policy-intake"]
            and parts[5] == "archive"
        ):
            sid = parts[4]
            if ".." in sid or not sid:
                self._json(400, {"ok": False, "error": "invalid_submission_id"}, no_cache=True)
                return
            body = self._read_json_body() or {}
            if "is_active" in body:
                is_active = bool(body.get("is_active"))
            elif body.get("archived") is True:
                is_active = False
            elif body.get("archived") is False:
                is_active = True
            else:
                is_active = False
            trace_id = str(uuid.uuid4())
            try:
                from renaissance_v4.policy_intake.candidates_registry import set_intake_candidate_active

                r = set_intake_candidate_active(_REPO_ROOT, sid, is_active=is_active)
            except Exception as e:  # noqa: BLE001
                self._json(500, {"ok": False, "error": str(e)[:500], "trace_id": trace_id}, no_cache=True)
                return
            if not r.get("ok"):
                self._json(400, {**r, "trace_id": trace_id}, no_cache=True)
                return
            r["trace_id"] = trace_id
            self._json(200, r, no_cache=True)
            return
        if len(parts) == 5 and parts[:2] == ["api", "v1"] and parts[2] == "agents":
            agent_id = parts[3].lower()
            action = parts[4].lower()
            if agent_id not in ALLOWED_AGENTS:
                self._json(404, {"error": "unknown_agent", "agent_id": agent_id})
                return
            if action not in ALLOWED_ACTIONS:
                self._json(400, {"error": "unsupported_action", "action": action})
                return
            result_state, reason = run_control(agent_id, action)
            self._json(
                200,
                {
                    "agent_id": agent_id,
                    "action": action,
                    "result_state": result_state,
                    "reason_code": reason,
                    "trace_id": str(uuid.uuid4()),
                    "emitted_at": now_iso(),
                },
            )
            return
        if len(parts) == 5 and parts[:2] == ["api", "v1"] and parts[2] == "sequential-learning" and parts[3] == "control":
            action = parts[4].lower()
            body = self._read_json_body()
            try:
                from modules.anna_training.sequential_engine import ui_control as seq_uc
            except Exception as e:  # noqa: BLE001
                self._json(500, {"ok": False, "reason_code": "SEQUENTIAL_IMPORT_FAIL", "detail": str(e)})
                return
            trace_id = str(uuid.uuid4())
            if action == "start":
                sm_raw = str(body.get("start_mode") or "resume").lower()
                sm: Any = "new_run" if sm_raw == "new_run" else "resume"
                try:
                    r = seq_uc.control_start(
                        start_mode=sm,
                        test_id=str(body.get("test_id") or ""),
                        strategy_id=str(body.get("strategy_id") or ""),
                        calibration_path=str(body.get("calibration_path") or ""),
                        events_file_path=str(body.get("events_file_path") or ""),
                        ledger_db_path=str(body.get("ledger_db_path") or ""),
                        market_db_path=str(body.get("market_db_path") or ""),
                        artifacts_dir=str(body.get("artifacts_dir") or ""),
                    )
                except ValueError as e:
                    self._json(
                        400,
                        {
                            "ok": False,
                            "reason_code": "calibration_validation_failed",
                            "detail": str(e),
                            "trace_id": trace_id,
                        },
                    )
                    return
                except Exception as e:  # noqa: BLE001 — calibration JSON / schema errors
                    en = type(e).__name__
                    if en in ("ValidationError", "JSONDecodeError") or "validation" in en.lower():
                        self._json(
                            400,
                            {
                                "ok": False,
                                "reason_code": "calibration_validation_failed",
                                "detail": str(e),
                                "trace_id": trace_id,
                            },
                        )
                        return
                    raise
                code = 200 if r.get("ok") else 400
                r["trace_id"] = trace_id
                self._json(code, r)
                return
            if action == "pause":
                r = seq_uc.control_pause()
                code = 200 if r.get("ok") else 409
                r["trace_id"] = trace_id
                self._json(code, r)
                return
            if action == "stop":
                r = seq_uc.control_stop()
                code = 200 if r.get("ok") else 409
                r["trace_id"] = trace_id
                self._json(code, r)
                return
            if action == "reset":
                r = seq_uc.control_reset(
                    archive=bool(body.get("archive", True)),
                    new_test_id=str(body.get("new_test_id") or "").strip() or None,
                )
                code = 200 if r.get("ok") else 409
                r["trace_id"] = trace_id
                self._json(code, r)
                return
            if action == "tick":
                r = seq_uc.control_tick(max_events=int(body.get("max_events") or 5))
                if r.get("reason_code") == "driver_exception":
                    code = 500
                elif r.get("ok") or r.get("reason_code") in ("end_of_events", "not_running_tick_skipped"):
                    code = 200
                else:
                    code = 400
                r["trace_id"] = trace_id
                self._json(code, r)
                return
            self._json(400, {"ok": False, "error": "unknown_action", "action": action, "trace_id": trace_id})
            return
        if len(parts) == 4 and parts[:2] == ["api", "v1"] and parts[2] == "paper-capital" and parts[3] == "flow":
            body = self._read_json_body()
            try:
                from modules.anna_training.paper_capital import append_flow

                r = append_flow(
                    event_type=str(body.get("event_type") or ""),
                    amount_usd=body.get("amount_usd"),
                    note=str(body.get("note") or ""),
                )
            except Exception as e:  # noqa: BLE001
                self._json(500, {"ok": False, "error": str(e)[:500]}, no_cache=True)
                return
            code = 200 if r.get("ok") else 400
            self._json(code, r, no_cache=True)
            return
        if len(parts) == 4 and parts[:2] == ["api", "v1"] and parts[2] == "paper-capital" and parts[3] == "set-starting":
            body = self._read_json_body()
            try:
                from modules.anna_training.paper_capital import replace_initial_capital

                raw_amt = body.get("starting_usd")
                if raw_amt is None:
                    raw_amt = body.get("amount_usd")
                r = replace_initial_capital(amount_usd=float(raw_amt or 0))
            except Exception as e:  # noqa: BLE001
                self._json(500, {"ok": False, "error": str(e)[:500]}, no_cache=True)
                return
            code = 200 if r.get("ok") else 400
            self._json(code, r, no_cache=True)
            return
        if len(parts) == 4 and parts[:2] == ["api", "v1"] and parts[2] == "operator" and parts[3] == "trading-strategy":
            body = self._read_json_body()
            trace_id = str(uuid.uuid4())
            try:
                from modules.anna_training.operator_trading_strategy import (
                    demote_designated_strategy,
                    promote_designated_strategy,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"ok": False, "reason_code": "import_fail", "detail": str(e)[:400], "trace_id": trace_id},
                    no_cache=True,
                )
                return
            action = str(body.get("action") or "").strip().lower()
            try:
                from modules.anna_training.execution_ledger import default_execution_ledger_path

                _ldb = default_execution_ledger_path()
            except Exception:
                _ldb = None
            if action == "promote":
                r = promote_designated_strategy(
                    strategy_id=str(body.get("strategy_id") or ""),
                    ledger_db_path=_ldb,
                )
            elif action == "demote":
                r = demote_designated_strategy(
                    strategy_id=str(body.get("strategy_id") or ""),
                    replacement_strategy_id=str(body.get("replacement_strategy_id") or ""),
                    ledger_db_path=_ldb,
                )
            else:
                self._json(
                    400,
                    {
                        "ok": False,
                        "reason_code": "unknown_action",
                        "detail": "action must be promote or demote",
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            code = 200 if r.get("ok") else 400
            r["trace_id"] = trace_id
            self._json(code, r, no_cache=True)
            return
        path_norm = (parsed.path or "").rstrip("/") or "/"
        if path_norm == "/api/v1/renaissance/kitchen-runtime-assignment":
            trace_id = str(uuid.uuid4())
            body = self._read_json_body() or {}
            sid = str(body.get("submission_id") or "").strip()
            et_raw = str(body.get("execution_target") or "").strip()
            if not sid:
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": "missing_submission_id",
                        "detail": "JSON body must include submission_id and execution_target",
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            if not et_raw:
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": "missing_execution_target",
                        "detail": "JSON body must include execution_target (jupiter | blackbox)",
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            try:
                from renaissance_v4.kitchen_runtime_assignment import assign_mechanical_candidate

                r = assign_mechanical_candidate(_REPO_ROOT, sid, et_raw)
            except ValueError as e:
                self._json(
                    400,
                    {"ok": False, "error": "invalid_execution_target", "detail": str(e)[:500], "trace_id": trace_id},
                    no_cache=True,
                )
                return
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"ok": False, "error": str(e)[:800], "trace_id": trace_id},
                    no_cache=True,
                )
                return
            r["trace_id"] = trace_id
            code = 200 if r.get("ok") else 400
            self._json(code, r, no_cache=True)
            return
        if path_norm == "/api/v1/renaissance/kitchen-assign-jupiter":
            trace_id = str(uuid.uuid4())
            body = self._read_json_body() or {}
            sid = str(body.get("submission_id") or "").strip()
            if not sid:
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": "missing_submission_id",
                        "detail": "JSON body must include submission_id (legacy alias: use kitchen-runtime-assignment with execution_target)",
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            try:
                from renaissance_v4.kitchen_runtime_assignment import assign_mechanical_candidate_to_jupiter

                r = assign_mechanical_candidate_to_jupiter(_REPO_ROOT, sid)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"ok": False, "error": str(e)[:800], "trace_id": trace_id},
                    no_cache=True,
                )
                return
            r["trace_id"] = trace_id
            r["note"] = "Deprecated alias: prefer POST /api/v1/renaissance/kitchen-runtime-assignment (DV-068)."
            code = 200 if r.get("ok") else 400
            self._json(code, r, no_cache=True)
            return
        if path_norm == "/api/v1/renaissance/policy-intake":
            ct = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ct != "multipart/form-data":
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": "expected_multipart_form_data",
                        "detail": "Use enctype multipart/form-data and field name policy_file",
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0 or n > 8 * 1024 * 1024:
                self._json(
                    400,
                    {"ok": False, "error": "invalid_content_length", "max_bytes": 8388608},
                    no_cache=True,
                )
                return
            body = self.rfile.read(n)
            full_ct = self.headers.get("Content-Type") or ""
            env = {
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": full_ct,
                "CONTENT_LENGTH": str(len(body)),
            }
            fs = cgi.FieldStorage(fp=io.BytesIO(body), environ=env, keep_blank_values=True)
            fn = None
            raw = b""
            if "policy_file" in fs:
                item = fs["policy_file"]
                fn = getattr(item, "filename", None) or None
                if hasattr(item, "file") and item.file:
                    raw = item.file.read()
                elif item.value:
                    raw = item.value if isinstance(item.value, bytes) else str(item.value).encode("utf-8")
            if not fn or not raw:
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": "missing_policy_file",
                        "detail": "Provide multipart field policy_file",
                        "trace_id": str(uuid.uuid4()),
                    },
                    no_cache=True,
                )
                return
            exec_raw = None
            if "execution_target" in fs:
                ex_item = fs["execution_target"]
                if hasattr(ex_item, "value"):
                    v = ex_item.value
                    exec_raw = v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v or "")
            trace_id = str(uuid.uuid4())
            try:
                from renaissance_v4.execution_targets import assert_baseline_for_intake, normalize_execution_target
                from renaissance_v4.policy_intake.pipeline import run_intake_pipeline

                try:
                    et = normalize_execution_target(exec_raw)
                except ValueError as ve:
                    self._json(
                        400,
                        {
                            "ok": False,
                            "error": "invalid_execution_target",
                            "detail": str(ve)[:500],
                            "trace_id": trace_id,
                        },
                        no_cache=True,
                    )
                    return
                try:
                    assert_baseline_for_intake(_REPO_ROOT, et)
                except ValueError as ve:
                    self._json(
                        503,
                        {
                            "ok": False,
                            "error": "baseline_missing_for_execution_target",
                            "detail": str(ve)[:1200],
                            "execution_target": et,
                            "trace_id": trace_id,
                        },
                        no_cache=True,
                    )
                    return
                rep = run_intake_pipeline(
                    _REPO_ROOT, raw, fn, test_window_bars=800, execution_target=et
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"ok": False, "error": str(e)[:800], "trace_id": trace_id},
                    no_cache=True,
                )
                return
            if isinstance(rep, dict):
                rep["trace_id"] = trace_id
            self._json(200, rep, no_cache=True)
            return
        if path_norm == "/api/v1/renaissance/promotion-approve":
            body = self._read_json_body() or {}
            trace_id = str(uuid.uuid4())
            parent = str(body.get("parent_hypothesis_id") or "").strip()
            try:
                from renaissance_v4.research.sra_handoff import approve_promotion

                r = approve_promotion(parent, repo_root=_REPO_ROOT, assigned_by="renaissance_api")
            except ValueError as e:
                self._json(
                    400,
                    {"ok": False, "error": str(e), "trace_id": trace_id},
                    no_cache=True,
                )
                return
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"ok": False, "error": str(e)[:500], "trace_id": trace_id},
                    no_cache=True,
                )
                return
            r["trace_id"] = trace_id
            self._json(200, r, no_cache=True)
            return
        if path_norm == "/api/v1/dashboard/baseline-chain-validate":
            body = self._read_json_body()
            trace_id = str(uuid.uuid4())
            try:
                from modules.anna_training.baseline_chain_validate import parse_request_body, validate_range

                kwargs = parse_request_body(body)
                out = validate_range(**kwargs)
            except ValueError as e:
                self._json(
                    400,
                    {
                        "schema": "baseline_chain_validate_v2",
                        "ok": False,
                        "error": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "schema": "baseline_chain_validate_v2",
                        "ok": False,
                        "error": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            if isinstance(out, dict):
                out["trace_id"] = trace_id
            self._json(200, out, no_cache=True)
            return
        # DV-ARCH-POLICY-LOAD-028: New/custom policy packages must go through Kitchen evaluation
        # (unified pipeline) before live assignment — do not use this endpoint as a package bypass.
        # This route only enqueues pending activation among built-in integrated slots (jup_v2|v3|v4).
        if path_norm == "/api/v1/dashboard/baseline-jupiter-policy":
            body = self._read_json_body() or {}
            trace_id = str(uuid.uuid4())
            try:
                from modules.anna_training.execution_ledger import (
                    baseline_jupiter_policy_label_for_slot,
                    baseline_jupiter_policy_lineage,
                    baseline_jupiter_policy_activation_api_snapshot,
                    connect_ledger,
                    default_execution_ledger_path,
                    enqueue_baseline_jupiter_policy_activation,
                    normalize_baseline_jupiter_policy_slot,
                    POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
                    ensure_execution_ledger_schema,
                )
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "ok": False,
                        "error": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            ldb = default_execution_ledger_path()
            try:
                conn = connect_ledger(ldb)
                try:
                    ensure_execution_ledger_schema(conn)
                    pid = str(body.get("policy_id") or "").strip()
                    pver = str(body.get("policy_version") or "").strip()
                    slot = str(body.get("slot") or "").strip()
                    if pid and pver and slot:
                        enqueue_baseline_jupiter_policy_activation(
                            conn,
                            policy_id=pid,
                            policy_version=pver,
                            slot=slot,
                            assigned_by="dashboard_api",
                        )
                    else:
                        raw_slot = str(body.get("policy_slot") or body.get("id") or "").strip().lower()
                        if not raw_slot:
                            raise ValueError(
                                "Provide policy_id, policy_version, and slot, or policy_slot (legacy)"
                            )
                        ps = normalize_baseline_jupiter_policy_slot(raw_slot)
                        if ps is None:
                            raise ValueError(
                                "policy_slot must be jup_v2, jup_v3, or jup_v4 (or aliases v2/v3/v4)"
                            )
                        lp = baseline_jupiter_policy_lineage(ps)
                        enqueue_baseline_jupiter_policy_activation(
                            conn,
                            policy_id=lp[0],
                            policy_version=lp[1],
                            slot=POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
                            assigned_by="dashboard_api",
                        )
                    conn.commit()
                    snap = baseline_jupiter_policy_activation_api_snapshot(conn)
                finally:
                    conn.close()
            except ValueError as e:
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": str(e),
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {
                        "ok": False,
                        "error": str(e)[:500],
                        "trace_id": trace_id,
                    },
                    no_cache=True,
                )
                return
            exec_slot = str(snap.get("effective_baseline_policy_slot") or "jup_v2")
            cap = snap.get("current_active_policy") or {}
            self._json(
                200,
                {
                    "ok": True,
                    "schema": "baseline_jupiter_policy_set_v2",
                    "current_active_policy": snap.get("current_active_policy"),
                    "pending_policy": snap.get("pending_policy"),
                    "effective_on": snap.get("effective_on"),
                    "active_id": exec_slot,
                    "active_label": baseline_jupiter_policy_label_for_slot(exec_slot),
                    "trace_id": trace_id,
                    "policy_id": cap.get("policy_id"),
                    "policy_version": cap.get("policy_version"),
                    "slot": cap.get("slot"),
                },
                no_cache=True,
            )
            return
        if parsed.path == "/api/v1/renaissance/jobs":
            body = self._read_json_body()
            try:
                from renaissance_v4.ui_api import (
                    validate_candidate_trades_path,
                    validate_experiment_id,
                    validate_job_action,
                    validate_manifest_path,
                    validate_policy_package_path,
                )
                from renaissance_v4.ui_jobs import enqueue

                action = str(body.get("action") or "").strip()
                if not validate_job_action(action):
                    self._json(
                        400,
                        {
                            "ok": False,
                            "error": "unsupported_action",
                            "allowed": [
                                "baseline_mc",
                                "compare",
                                "compare_manifest",
                                "example_flow",
                                "ingest_policy",
                            ],
                            "trace_id": str(uuid.uuid4()),
                        },
                        no_cache=True,
                    )
                    return
                exp = body.get("experiment_id")
                exp_s = str(exp).strip() if exp else None
                if action == "compare":
                    if not exp_s or not validate_experiment_id(exp_s):
                        self._json(
                            400,
                            {"ok": False, "error": "experiment_id_required", "trace_id": str(uuid.uuid4())},
                            no_cache=True,
                        )
                        return
                    ct = str(body.get("candidate_trades") or "").strip()
                    if not ct or validate_candidate_trades_path(_REPO_ROOT, ct) is None:
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": "candidate_trades_must_be_under_renaissance_v4/reports/experiments/",
                                "trace_id": str(uuid.uuid4()),
                            },
                            no_cache=True,
                        )
                        return
                    job = enqueue(
                        _REPO_ROOT,
                        action=action,
                        experiment_id=exp_s,
                        candidate_trades_rel=ct,
                    )
                elif action == "compare_manifest":
                    if not exp_s or not validate_experiment_id(exp_s):
                        self._json(
                            400,
                            {"ok": False, "error": "experiment_id_required", "trace_id": str(uuid.uuid4())},
                            no_cache=True,
                        )
                        return
                    mf = str(body.get("manifest") or body.get("manifest_path") or "").strip()
                    if not mf or validate_manifest_path(_REPO_ROOT, mf) is None:
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": "manifest_must_be_under_renaissance_v4/configs/manifests/",
                                "trace_id": str(uuid.uuid4()),
                            },
                            no_cache=True,
                        )
                        return
                    job = enqueue(
                        _REPO_ROOT,
                        action=action,
                        experiment_id=exp_s,
                        manifest_rel=mf,
                    )
                elif action == "ingest_policy":
                    if not exp_s or not validate_experiment_id(exp_s):
                        self._json(
                            400,
                            {"ok": False, "error": "experiment_id_required", "trace_id": str(uuid.uuid4())},
                            no_cache=True,
                        )
                        return
                    pr = str(body.get("policy_path") or "").strip()
                    if not pr or validate_policy_package_path(_REPO_ROOT, pr) is None:
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": "policy_path_must_be_policies_directory_with_POLICY_SPEC_yaml",
                                "trace_id": str(uuid.uuid4()),
                            },
                            no_cache=True,
                        )
                        return
                    job = enqueue(
                        _REPO_ROOT,
                        action=action,
                        experiment_id=exp_s,
                        policy_path_rel=pr,
                    )
                else:
                    job = enqueue(
                        _REPO_ROOT,
                        action=action,
                        experiment_id=exp_s,
                        candidate_trades_rel=None,
                    )
                self._json(200, {"ok": True, "job": job, "trace_id": str(uuid.uuid4())}, no_cache=True)
            except Exception as e:  # noqa: BLE001
                self._json(
                    500,
                    {"ok": False, "error": str(e)[:500], "trace_id": str(uuid.uuid4())},
                    no_cache=True,
                )
            return
        self._json(404, {"error": "not_found", "path": parsed.path})

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"UI truth API listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
