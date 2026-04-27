"""
RM preflight — bounded in-memory wiring validation before parallel batch (Directive: reasoning_model).

* Shrinks the evaluation calendar window (default **1** month; ``PATTERN_GAME_RM_PREFLIGHT_MAX_CALENDAR_MONTHS``).
* Caps the Referee tape to the **last N** bars (default **80**; ``PATTERN_GAME_RM_PREFLIGHT_REPLAY_TAIL_BARS``)
  so preflight stays **seconds-scale**. Worker wall time is capped via ``PATTERN_GAME_RM_PREFLIGHT_WORKER_TIMEOUT_S``
  (default **10**). Heartbeats update ``telemetry_v1`` on the Results panel while work runs.
* Runs **one** in-process worker row (same ``_worker_run_one`` as production) on the clamped scenario.
* Runs **one** Student seam pass with memory trace sink + early exit after first ``student_output_sealed``.
* Validates required RM trace stages in the sink — **no** ``learning_trace_events_v1.jsonl`` writes.

Baseline may disable with ``PATTERN_GAME_RM_PREFLIGHT=0``. Non-baseline Student runs cannot
skip RM preflight via env (contract).
"""

from __future__ import annotations

import copy
import os
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    normalize_student_reasoning_mode_v1,
)
from renaissance_v4.game_theory.learning_trace_events_v1 import learning_trace_memory_sink_session_v1
from renaissance_v4.game_theory.parallel_runner import _normalize_scenario, _worker_run_one
from renaissance_v4.game_theory.rm_preflight_context_v1 import rm_preflight_seam_early_exit_session_v1
from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
    DECISION_SOURCE_REASONING_MODEL_V1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
)

FAILED_PREFLIGHT_STATUS_V1 = "failed_preflight_reasoning_model_v1"


def _preflight_cancel_hit_v1(cancel_check: Callable[[], bool] | None) -> bool:
    if cancel_check is None:
        return False
    try:
        return bool(cancel_check())
    except Exception:
        return False


def _operator_cancelled_preflight_audit_v1(
    *,
    memory_sink_event_count_v1: int = 0,
    message: str = "Stopped by operator during RM preflight — parallel workers were not started.",
) -> dict[str, Any]:
    """Operator cancel is not a wiring failure; ``run_job`` branches on ``cancelled_during_preflight_v1``."""
    return {
        "schema": "rm_preflight_wiring_audit_v1",
        "ok_v1": False,
        "skipped_v1": False,
        "cancelled_during_preflight_v1": True,
        "status_v1": None,
        "missing_stages_v1": [],
        "human_message_v1": message,
        "memory_sink_event_count_v1": int(memory_sink_event_count_v1),
    }

# Required trace stages for one trade (referee check is payload under authority, not a separate stage).
REQUIRED_RM_PREFLIGHT_STAGES_V1 = frozenset(
    {
        "entry_reasoning_sealed_v1",
        "reasoning_router_decision_v1",
        "reasoning_cost_governor_v1",
        "student_decision_authority_v1",
        "student_output_sealed",
    }
)


def rm_preflight_enabled_v1() -> bool:
    v = os.environ.get("PATTERN_GAME_RM_PREFLIGHT", "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _env_seam_enabled() -> bool:
    v = os.environ.get("PATTERN_GAME_STUDENT_LOOP_SEAM", "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _shrink_scenario_for_rm_preflight_v1(scenario: dict[str, Any]) -> dict[str, Any]:
    """
    Tighten calendar window and attach a **tail bar cap** so preflight replay stays bounded.

    Defaults target **seconds-scale** wiring checks (not full operator replays). Override with env:

    * ``PATTERN_GAME_RM_PREFLIGHT_MAX_CALENDAR_MONTHS`` (default **1**)
    * ``PATTERN_GAME_RM_PREFLIGHT_REPLAY_TAIL_BARS`` (default **80**; min 50, max 250000)
    """
    s = copy.deepcopy(scenario)
    try:
        cap = int(os.environ.get("PATTERN_GAME_RM_PREFLIGHT_MAX_CALENDAR_MONTHS", "1"))
    except (TypeError, ValueError):
        cap = 1
    cap = max(1, min(cap, 24))
    ew_prev = s.get("evaluation_window") if isinstance(s.get("evaluation_window"), dict) else {}
    ew = dict(ew_prev)
    cm0 = ew.get("calendar_months")
    try:
        cur = int(cm0) if cm0 is not None else cap
    except (TypeError, ValueError):
        cur = cap
    ew["calendar_months"] = max(1, min(cur, cap))
    ew["rm_preflight_window_clamp_v1"] = True
    s["evaluation_window"] = ew
    try:
        tail = int(os.environ.get("PATTERN_GAME_RM_PREFLIGHT_REPLAY_TAIL_BARS", "80"))
    except (TypeError, ValueError):
        tail = 80
    tail = max(50, min(tail, 250_000))
    s["rm_preflight_replay_tail_bars_v1"] = tail
    return s


def _rm_preflight_worker_timeout_seconds_v1() -> float:
    raw = (os.environ.get("PATTERN_GAME_RM_PREFLIGHT_WORKER_TIMEOUT_S") or "10").strip()
    try:
        t = float(raw)
    except (TypeError, ValueError):
        t = 10.0
    return max(3.0, min(t, 120.0))


def _rm_preflight_heartbeat_interval_s_v1() -> float:
    raw = (os.environ.get("PATTERN_GAME_RM_PREFLIGHT_HEARTBEAT_INTERVAL_S") or "1.25").strip()
    try:
        t = float(raw)
    except (TypeError, ValueError):
        t = 1.25
    return max(0.5, min(t, 5.0))


def _preflight_telemetry_update_v1(
    panel: dict[str, Any],
    *,
    phase: str,
    t0: float,
    bars_replay_cap: int | None,
    bars_processed: int | None = None,
    heartbeat_seq: int | None = None,
    note: str | None = None,
) -> None:
    tel = panel.setdefault("telemetry_v1", {})
    tel["schema"] = "rm_preflight_telemetry_v1"
    tel["phase_v1"] = str(phase or "")[:64]
    tel["elapsed_s_v1"] = round(time.monotonic() - t0, 2)
    if bars_replay_cap is not None:
        tel["bars_replay_cap_v1"] = int(bars_replay_cap)
    if bars_processed is not None:
        tel["bars_processed_v1"] = int(bars_processed)
    if heartbeat_seq is not None:
        tel["heartbeat_seq_v1"] = int(heartbeat_seq)
    if note:
        tel["note_v1"] = str(note)[:240]
    if bars_replay_cap is not None:
        tel["replay_position_v1"] = f"tail_last_{int(bars_replay_cap)}_bars_v1"


def _rm_preflight_by_stage_for_trade_v1(
    events: list[dict[str, Any]],
    *,
    scenario_id: str,
    trade_id: str,
) -> dict[str, list[dict[str, Any]]]:
    sid = str(scenario_id or "").strip()
    tid = str(trade_id or "").strip()
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        if str(ev.get("scenario_id") or "").strip() != sid:
            continue
        if str(ev.get("trade_id") or "").strip() != tid:
            continue
        st = str(ev.get("stage") or "").strip()
        if st:
            by_stage[st].append(ev)
    return by_stage


def validate_rm_preflight_memory_sink_detailed_v1(
    events: list[dict[str, Any]],
    *,
    scenario_id: str,
    trade_id: str,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Full sink validation + per-stage counts for operator Results panel (preflight proof)."""
    sid = str(scenario_id or "").strip()
    tid = str(trade_id or "").strip()
    jid = str(job_id or "").strip()
    by_stage = _rm_preflight_by_stage_for_trade_v1(events, scenario_id=sid, trade_id=tid)
    missing: list[str] = []
    if jid:
        for st in sorted(REQUIRED_RM_PREFLIGHT_STAGES_V1):
            for ev in by_stage.get(st, ()):
                ev_j = str(ev.get("job_id") or "").strip()
                if not ev_j:
                    missing.append("missing_job_id")
                elif ev_j != jid:
                    missing.append(f"job_id_not_bound_v1:{st}")
    for st in sorted(REQUIRED_RM_PREFLIGHT_STAGES_V1):
        if st not in by_stage:
            missing.append(st)
    auth_rows = by_stage.get("student_decision_authority_v1") or []
    if not auth_rows:
        missing.append("referee_safety_check_v1")
    else:
        pl = (auth_rows[-1].get("evidence_payload") or {}).get("student_decision_authority_v1") or {}
        if not isinstance(pl, dict):
            missing.append("referee_safety_check_v1")
        else:
            ref = pl.get("referee_safety_check_v1")
            if not isinstance(ref, dict) or "passed_v1" not in ref:
                missing.append("referee_safety_check_v1")
            if pl.get("decision_source_v1") != DECISION_SOURCE_REASONING_MODEL_V1:
                missing.append("student_decision_authority_v1.decision_source_v1_reasoning_model")
    sealed_rows = by_stage.get("student_output_sealed") or []
    if not sealed_rows:
        missing.append("student_output_sealed.decision_source_v1")
    else:
        sev = sealed_rows[-1].get("evidence_payload") if isinstance(sealed_rows[-1].get("evidence_payload"), dict) else {}
        if sev.get("decision_source_v1") != DECISION_SOURCE_REASONING_MODEL_V1:
            missing.append("student_output_sealed.decision_source_v1_reasoning_model")
        elif sev.get("student_decision_protocol_ok_v1") is not True:
            missing.append("student_output_sealed.student_decision_protocol_incomplete_v1")
    missing_u = sorted(set(missing))
    job_id_binding_ok_v1 = bool(jid) and not any(
        m == "missing_job_id" or (isinstance(m, str) and m.startswith("job_id_not_bound_v1:")) for m in missing_u
    )
    stage_counts = {st: len(by_stage.get(st, ())) for st in sorted(REQUIRED_RM_PREFLIGHT_STAGES_V1)}
    ds_rm = 0
    for st in ("student_decision_authority_v1", "student_output_sealed"):
        for ev in by_stage.get(st, ()):
            ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
            if st == "student_decision_authority_v1":
                inner = ep.get("student_decision_authority_v1") if isinstance(ep.get("student_decision_authority_v1"), dict) else {}
                if inner.get("decision_source_v1") == DECISION_SOURCE_REASONING_MODEL_V1:
                    ds_rm += 1
            elif ep.get("decision_source_v1") == DECISION_SOURCE_REASONING_MODEL_V1:
                ds_rm += 1
    auth_n = len(auth_rows)
    sealed_n = len(sealed_rows)
    mismatch = abs(auth_n - sealed_n) if (auth_n or sealed_n) else 0
    if auth_n and sealed_n and auth_n != sealed_n:
        mismatch = max(mismatch, 1)
    return {
        "schema": "rm_preflight_memory_sink_detail_v1",
        "ok_v1": len(missing_u) == 0,
        "missing_stages_v1": missing_u,
        "job_id_binding_ok_v1": job_id_binding_ok_v1,
        "stage_event_counts_v1": stage_counts,
        "decision_source_reasoning_model_count_v1": ds_rm,
        "authority_events_for_trade_v1": auth_n,
        "sealed_output_events_for_trade_v1": sealed_n,
        "breadcrumb_mismatch_count_v1": int(mismatch),
    }


def _new_rm_preflight_results_panel_v1(job_id: str) -> dict[str, Any]:
    return {
        "schema": "rm_preflight_results_panel_v1",
        "job_id": str(job_id or "").strip(),
        "active_scenario_id_v1": None,
        "active_trade_id_v1": None,
        "stages_v1": {
            "started_v1": False,
            "scenario_bound_v1": False,
            "trade_bound_v1": False,
            "seam_completed_v1": False,
            "job_id_bound_trace_v1": None,
            "breadcrumbs_validated_v1": None,
            "terminal_pass_v1": None,
        },
        "lines_v1": [],
        "failure_reasons_display_v1": [],
        "preflight_sink_detail_v1": None,
    }


def _finalize_rm_preflight_results_lines_v1(panel: dict[str, Any]) -> None:
    """Rebuild ``lines_v1`` from stages (operator-facing checklist order)."""
    jid = str(panel.get("job_id") or "")
    s = panel.setdefault("stages_v1", {})
    sid = panel.get("active_scenario_id_v1")
    tid = panel.get("active_trade_id_v1")
    lines: list[str] = [
        "RM PREFLIGHT STARTED",
        f"job_id={jid}",
    ]
    s.setdefault("started_v1", True)

    # User-required order: JOB BOUND, SCENARIO BOUND, TRADE BOUND, BREADCRUMBS, then PASS/FAIL
    jb = s.get("job_id_bound_trace_v1")
    if jb is True:
        lines.append("RM PREFLIGHT JOB BOUND — batch job_id present on all required RM trace rows (sink) ✓")
    elif jb is False:
        lines.append("RM PREFLIGHT JOB BOUND — FAIL (shell not coupled to trace job_id)")
    else:
        lines.append("RM PREFLIGHT JOB BOUND — PENDING (after seam + trace validation)")

    if s.get("scenario_bound_v1"):
        lines.append(f"RM PREFLIGHT SCENARIO BOUND — scenario_id={sid!r} matches first submitted scenario ✓")
    elif s.get("scenario_bound_failed_v1"):
        lines.append("RM PREFLIGHT SCENARIO BOUND — FAIL (scenario mismatch)")
    else:
        lines.append("RM PREFLIGHT SCENARIO BOUND — PENDING")

    if s.get("trade_bound_v1"):
        lines.append(f"RM PREFLIGHT TRADE BOUND — trade_id={tid!r} from first replay outcome ✓")
    elif s.get("trade_bound_failed_v1"):
        lines.append("RM PREFLIGHT TRADE BOUND — FAIL (trade_id missing or invalid)")
    else:
        lines.append("RM PREFLIGHT TRADE BOUND — PENDING")

    bc = s.get("breadcrumbs_validated_v1")
    if bc is True:
        lines.append("RM PREFLIGHT BREADCRUMBS VALIDATED — required RM stages + referee + decision_source ✓")
    elif bc is False:
        lines.append("RM PREFLIGHT BREADCRUMBS VALIDATED — FAIL (missing or invalid reasoning stages)")
    else:
        lines.append("RM PREFLIGHT BREADCRUMBS VALIDATED — PENDING")

    tp = s.get("terminal_pass_v1")
    if tp is True:
        lines.append("RM PREFLIGHT PASS — parallel workers may start")
    elif tp is False:
        lines.append("RM PREFLIGHT FAIL — parallel workers will NOT start")
    else:
        lines.append("RM PREFLIGHT — terminal state PENDING")

    fr = panel.get("failure_reasons_display_v1")
    if isinstance(fr, list) and fr:
        lines.append("FAILURE (from preflight audit / trace sink):")
        for x in fr:
            lines.append("  · " + str(x))
    panel["lines_v1"] = lines


def _emit_rm_preflight_panel_v1(
    panel: dict[str, Any],
    progress_cb: Callable[[dict[str, Any]], None] | None,
) -> None:
    _finalize_rm_preflight_results_lines_v1(panel)
    if progress_cb is None:
        return
    try:
        progress_cb(copy.deepcopy(panel))
    except Exception:
        pass


def _merge_panel_into_audit_v1(panel: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    _finalize_rm_preflight_results_lines_v1(panel)
    audit["rm_preflight_results_panel_v1"] = copy.deepcopy(panel)
    return audit


def map_rm_preflight_missing_to_operator_display_v1(missing: list[str]) -> list[str]:
    """Map internal missing codes to operator-facing failure lines (Results panel)."""
    out: list[str] = []
    for m in missing:
        s = str(m)
        if s == "missing_job_id":
            out.append("missing job_id")
        elif s.startswith("job_id_not_bound_v1:"):
            out.append("job_id_not_bound_v1 (" + s.split(":", 1)[-1] + ")")
        elif s == "job_binding_scenario_mismatch_v1":
            out.append("scenario mismatch")
        elif s == "job_binding_empty_trade_id_v1":
            out.append("trade_id missing")
        elif s == "entry_reasoning_sealed_v1":
            out.append("missing entry reasoning")
        elif s == "reasoning_router_decision_v1":
            out.append("missing router decision")
        elif s == "reasoning_cost_governor_v1":
            out.append("missing cost governor")
        elif s == "student_decision_authority_v1":
            out.append("missing student decision authority")
        elif s == "referee_safety_check_v1":
            out.append("missing safety check")
        elif s == "student_decision_authority_v1.decision_source_v1_reasoning_model":
            out.append("missing decision_source_v1: reasoning_model (authority)")
        elif s in (
            "student_output_sealed.decision_source_v1",
            "student_output_sealed.decision_source_v1_reasoning_model",
        ):
            out.append("missing decision_source_v1: reasoning_model (sealed)")
        elif s == "student_output_sealed.student_decision_protocol_incomplete_v1":
            out.append("Student decision protocol incomplete on sealed output (RM preflight)")
        elif s == "preflight_timeout_waiting_for_trade_v1":
            out.append(
                "RM preflight worker timeout — bounded replay did not finish within "
                "PATTERN_GAME_RM_PREFLIGHT_WORKER_TIMEOUT_S (see telemetry)"
            )
        else:
            out.append(s)
    return out


def validate_rm_preflight_memory_sink_v1(
    events: list[dict[str, Any]],
    *,
    scenario_id: str,
    trade_id: str,
    job_id: str | None = None,
) -> tuple[bool, list[str]]:
    det = validate_rm_preflight_memory_sink_detailed_v1(
        events, scenario_id=scenario_id, trade_id=trade_id, job_id=job_id
    )
    return bool(det.get("ok_v1")), list(det.get("missing_stages_v1") or [])


def _rm_preflight_job_binding_audit_v1(
    *,
    job_id: str,
    batch_first_scenario_id_v1: str,
    worker_row_scenario_id_v1: str,
    trade_id_v1: str,
    scenario_binding_ok_v1: bool,
    trace_job_binding_ok_v1: bool | None = None,
) -> dict[str, Any]:
    return {
        "schema": "rm_preflight_job_binding_audit_v1",
        "job_id": str(job_id).strip(),
        "batch_first_scenario_id_v1": str(batch_first_scenario_id_v1),
        "worker_row_scenario_id_v1": str(worker_row_scenario_id_v1),
        "trade_id_v1": str(trade_id_v1),
        "scenario_binding_ok_v1": bool(scenario_binding_ok_v1),
        "trace_job_binding_ok_v1": trace_job_binding_ok_v1,
    }


def should_skip_rm_preflight_v1(
    *,
    exam_run_contract_request_v1: dict[str, Any] | None,
) -> str | None:
    """Return skip reason string, or None if preflight should run.

    Non-baseline Student (RM wiring mandate): preflight is never skipped for ``rm_preflight_disabled``;
    seam disabled or env RM off yields a **fatal** reason handled in ``run_rm_preflight_wiring_v1``.
    """
    ex_req = exam_run_contract_request_v1 if isinstance(exam_run_contract_request_v1, dict) else None
    profile = normalize_student_reasoning_mode_v1(
        str((ex_req or {}).get("student_brain_profile_v1") or (ex_req or {}).get("student_reasoning_mode") or "")
    )
    if profile == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
        if not rm_preflight_enabled_v1():
            return "rm_preflight_disabled_v1"
        if not _env_seam_enabled():
            return "student_loop_seam_disabled_v1"
        return "baseline_no_student_mandate_v1"
    if not _env_seam_enabled():
        return "student_loop_seam_disabled_student_rm_contract_v1"
    if not rm_preflight_enabled_v1():
        return "rm_preflight_disabled_student_rm_contract_v1"
    return None


def run_rm_preflight_wiring_v1(
    *,
    scenarios: list[dict[str, Any]],
    job_id: str,
    exam_run_contract_request_v1: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    cancel_check: Callable[[], bool] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Returns ``ok_v1`` False on any failure (worker, seam, or missing trace stages).

    On success, ``skipped_v1`` may still be True when policy skips preflight.

    When ``cancel_check`` returns True, returns ``cancelled_during_preflight_v1`` so the caller can
    finalize the job as **cancelled** without starting ``run_scenarios_parallel``.

    ``progress_cb`` receives ``rm_preflight_results_panel_v1`` snapshots (deepcopy) for operator UI.
    """
    if _preflight_cancel_hit_v1(cancel_check):
        return _operator_cancelled_preflight_audit_v1()
    skip = should_skip_rm_preflight_v1(exam_run_contract_request_v1=exam_run_contract_request_v1)
    if skip:
        if skip in (
            "student_loop_seam_disabled_student_rm_contract_v1",
            "rm_preflight_disabled_student_rm_contract_v1",
        ):
            human = (
                "Student RM contract: non-baseline run requires RM preflight and student loop seam. "
                + (
                    "Enable PATTERN_GAME_STUDENT_LOOP_SEAM (non-zero)."
                    if "seam" in skip
                    else "Do not set PATTERN_GAME_RM_PREFLIGHT=0 for non-baseline Student runs."
                )
            )
            return {
                "schema": "rm_preflight_wiring_audit_v1",
                "ok_v1": False,
                "skipped_v1": False,
                "skip_reason_v1": skip,
                "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                "missing_stages_v1": [skip],
                "human_message_v1": human,
                "memory_sink_event_count_v1": 0,
            }
        out_skip = {
            "schema": "rm_preflight_wiring_audit_v1",
            "ok_v1": True,
            "skipped_v1": True,
            "skip_reason_v1": skip,
            "status_v1": None,
            "missing_stages_v1": [],
            "memory_sink_event_count_v1": 0,
        }
        if _preflight_cancel_hit_v1(cancel_check):
            return _operator_cancelled_preflight_audit_v1()
        return out_skip
    if not scenarios:
        return {
            "schema": "rm_preflight_wiring_audit_v1",
            "ok_v1": False,
            "skipped_v1": False,
            "status_v1": FAILED_PREFLIGHT_STATUS_V1,
            "missing_stages_v1": ["no_scenarios"],
            "human_message_v1": "RM preflight: empty scenario list.",
            "memory_sink_event_count_v1": 0,
        }

    scen0 = _normalize_scenario(scenarios[0])
    shrunk = _shrink_scenario_for_rm_preflight_v1(scen0)

    with learning_trace_memory_sink_session_v1() as sink:
        panel = _new_rm_preflight_results_panel_v1(str(job_id).strip())
        st = panel["stages_v1"]
        st["started_v1"] = True
        _emit_rm_preflight_panel_v1(panel, progress_cb)

        if _preflight_cancel_hit_v1(cancel_check):
            st["terminal_pass_v1"] = False
            panel["failure_reasons_display_v1"] = ["cancelled_before_worker"]
            return _merge_panel_into_audit_v1(
                panel,
                _operator_cancelled_preflight_audit_v1(memory_sink_event_count_v1=len(sink)),
            )

        tail_cap_raw = shrunk.get("rm_preflight_replay_tail_bars_v1")
        try:
            bars_cap = int(tail_cap_raw) if tail_cap_raw is not None else 80
        except (TypeError, ValueError):
            bars_cap = 80
        t0 = time.monotonic()
        phase_holder: dict[str, Any] = {"v": "worker_replay"}
        hb_done = threading.Event()

        def _preflight_hb_loop_v1() -> None:
            iv = _rm_preflight_heartbeat_interval_s_v1()
            seq = 0
            while not hb_done.wait(timeout=iv):
                if _preflight_cancel_hit_v1(cancel_check):
                    break
                seq += 1
                _preflight_telemetry_update_v1(
                    panel,
                    phase=str(phase_holder.get("v") or "worker_replay"),
                    t0=t0,
                    bars_replay_cap=bars_cap,
                    heartbeat_seq=seq,
                    note="rm_preflight_heartbeat_v1",
                )
                _emit_rm_preflight_panel_v1(panel, progress_cb)

        _preflight_telemetry_update_v1(
            panel,
            phase="starting",
            t0=t0,
            bars_replay_cap=bars_cap,
            heartbeat_seq=0,
            note="bounded_worker_then_seam",
        )
        _emit_rm_preflight_panel_v1(panel, progress_cb)
        _hb_t = threading.Thread(target=_preflight_hb_loop_v1, daemon=True, name="rm_preflight_hb_v1")
        _hb_t.start()
        try:
            _ex = ThreadPoolExecutor(max_workers=1)
            try:
                _fut = _ex.submit(_worker_run_one, shrunk)
                row = _fut.result(timeout=_rm_preflight_worker_timeout_seconds_v1())
            except FuturesTimeoutError:
                st["terminal_pass_v1"] = False
                phase_holder["v"] = "preflight_timeout"
                _preflight_telemetry_update_v1(
                    panel,
                    phase="preflight_timeout",
                    t0=t0,
                    bars_replay_cap=bars_cap,
                    heartbeat_seq=None,
                    note="preflight_timeout_waiting_for_trade_v1",
                )
                panel["failure_reasons_display_v1"] = map_rm_preflight_missing_to_operator_display_v1(
                    ["preflight_timeout_waiting_for_trade_v1"]
                )
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["preflight_timeout_waiting_for_trade_v1"],
                        "human_message_v1": (
                            "RM preflight: bounded replay exceeded "
                            f"{_rm_preflight_worker_timeout_seconds_v1():.0f}s "
                            "(see PATTERN_GAME_RM_PREFLIGHT_WORKER_TIMEOUT_S); "
                            "try a smaller PATTERN_GAME_RM_PREFLIGHT_REPLAY_TAIL_BARS."
                        ),
                        "memory_sink_event_count_v1": len(sink),
                    },
                )
            finally:
                _ex.shutdown(wait=False, cancel_futures=False)

            phase_holder["v"] = "replay_complete"
            _ds_bars = row.get("dataset_bars")
            _ds_bars2 = row.get("dataset_bars_after_rollup")
            _bars_proc = _ds_bars if _ds_bars is not None else _ds_bars2
            _preflight_telemetry_update_v1(
                panel,
                phase="replay_complete",
                t0=t0,
                bars_replay_cap=bars_cap,
                bars_processed=int(_bars_proc)
                if isinstance(_bars_proc, (int, float)) and not isinstance(_bars_proc, bool)
                else None,
                note="worker_row_returned",
            )
            _emit_rm_preflight_panel_v1(panel, progress_cb)

            if _preflight_cancel_hit_v1(cancel_check):
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = ["cancelled_after_worker"]
                return _merge_panel_into_audit_v1(
                    panel,
                    _operator_cancelled_preflight_audit_v1(memory_sink_event_count_v1=len(sink)),
                )

            if not row.get("ok"):
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = [
                    "preflight_worker_row_failed_v1",
                    str(row.get("error") or "worker row not ok"),
                ]
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["preflight_worker_row_failed_v1"],
                        "human_message_v1": str(row.get("error") or "worker row not ok"),
                        "memory_sink_event_count_v1": len(sink),
                        "preflight_worker_scenario_id_v1": str(row.get("scenario_id") or ""),
                    },
                )

            expected_batch_scenario_id_v1 = shrunk.get("scenario_id", "unknown")
            row_sid = row.get("scenario_id")
            if str(row_sid) != str(expected_batch_scenario_id_v1):
                st["scenario_bound_failed_v1"] = True
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = map_rm_preflight_missing_to_operator_display_v1(
                    ["job_binding_scenario_mismatch_v1"]
                )
                jbind = _rm_preflight_job_binding_audit_v1(
                    job_id=str(job_id).strip(),
                    batch_first_scenario_id_v1=str(expected_batch_scenario_id_v1),
                    worker_row_scenario_id_v1=str(row_sid),
                    trade_id_v1="",
                    scenario_binding_ok_v1=False,
                    trace_job_binding_ok_v1=None,
                )
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["job_binding_scenario_mismatch_v1"],
                        "human_message_v1": (
                            "RM preflight: worker scenario_id does not match first submitted scenario "
                            f"(batch_first={expected_batch_scenario_id_v1!r}, row={row_sid!r})."
                        ),
                        "memory_sink_event_count_v1": len(sink),
                        "rm_preflight_job_binding_audit_v1": jbind,
                    },
                )

            st["scenario_bound_v1"] = True
            panel["active_scenario_id_v1"] = str(row_sid or "").strip()
            _emit_rm_preflight_panel_v1(panel, progress_cb)

            raw_out = row.get("replay_outcomes_json")
            if not isinstance(raw_out, list) or not raw_out:
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = ["no_replay_outcomes_for_preflight_v1"]
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["no_replay_outcomes_for_preflight_v1"],
                        "human_message_v1": "RM preflight: bounded replay returned no closed trades.",
                        "memory_sink_event_count_v1": len(sink),
                    },
                )
            first = raw_out[0]
            if not isinstance(first, dict):
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = ["invalid_first_outcome_v1"]
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["invalid_first_outcome_v1"],
                        "human_message_v1": "RM preflight: first outcome is not a dict.",
                        "memory_sink_event_count_v1": len(sink),
                    },
                )
            trade_id = str(first.get("trade_id") or "").strip()
            scenario_id = str(row.get("scenario_id") or "").strip()
            if not trade_id:
                st["trade_bound_failed_v1"] = True
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = map_rm_preflight_missing_to_operator_display_v1(
                    ["job_binding_empty_trade_id_v1"]
                )
                jbind = _rm_preflight_job_binding_audit_v1(
                    job_id=str(job_id).strip(),
                    batch_first_scenario_id_v1=str(expected_batch_scenario_id_v1),
                    worker_row_scenario_id_v1=str(row_sid),
                    trade_id_v1="",
                    scenario_binding_ok_v1=True,
                    trace_job_binding_ok_v1=None,
                )
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["job_binding_empty_trade_id_v1"],
                        "human_message_v1": "RM preflight: first replay outcome has no trade_id — cannot bind RM trace to a shell.",
                        "memory_sink_event_count_v1": len(sink),
                        "rm_preflight_job_binding_audit_v1": jbind,
                    },
                )

            st["trade_bound_v1"] = True
            panel["active_trade_id_v1"] = trade_id
            _emit_rm_preflight_panel_v1(panel, progress_cb)

            n_sink_before_seam = len(sink)
            if _preflight_cancel_hit_v1(cancel_check):
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = ["cancelled_before_seam"]
                return _merge_panel_into_audit_v1(
                    panel,
                    _operator_cancelled_preflight_audit_v1(memory_sink_event_count_v1=len(sink)),
                )
            phase_holder["v"] = "student_seam"
            _preflight_telemetry_update_v1(
                panel,
                phase="student_seam",
                t0=t0,
                bars_replay_cap=bars_cap,
                bars_processed=int(_bars_proc)
                if isinstance(_bars_proc, (int, float)) and not isinstance(_bars_proc, bool)
                else None,
                note="student_loop_seam_early_exit",
            )
            _emit_rm_preflight_panel_v1(panel, progress_cb)
            with rm_preflight_seam_early_exit_session_v1():
                seam = student_loop_seam_after_parallel_batch_v1(
                    results=[row],
                    run_id=str(job_id).strip(),
                    exam_run_contract_request_v1=exam_run_contract_request_v1,
                    operator_batch_audit=operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
                )
            if _preflight_cancel_hit_v1(cancel_check):
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = ["cancelled_after_seam"]
                return _merge_panel_into_audit_v1(
                    panel,
                    _operator_cancelled_preflight_audit_v1(memory_sink_event_count_v1=len(sink)),
                )
            st["seam_completed_v1"] = True
            _emit_rm_preflight_panel_v1(panel, progress_cb)

            if seam.get("skipped"):
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = [str(seam.get("reason") or "student_seam_skipped_v1")]
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["student_seam_skipped_v1"],
                        "human_message_v1": str(seam.get("reason") or "seam skipped"),
                        "memory_sink_event_count_v1": len(sink),
                        "preflight_seam_audit_v1": seam,
                    },
                )
            if not seam.get("rm_preflight_wiring_early_exit_v1"):
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = list(
                    map_rm_preflight_missing_to_operator_display_v1(["rm_preflight_early_exit_not_reached_v1"])
                ) + [str(x) for x in (seam.get("errors") or [])[:6]]
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["rm_preflight_early_exit_not_reached_v1"],
                        "human_message_v1": (
                            "RM preflight: first trade did not reach student_output_sealed — "
                            + "; ".join(str(x) for x in (seam.get("errors") or [])[:8])
                        ),
                        "memory_sink_event_count_v1": len(sink),
                        "preflight_seam_audit_v1": seam,
                    },
                )
            seam_errs = [str(x) for x in (seam.get("errors") or []) if x]
            if seam_errs:
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = seam_errs[:12]
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": ["student_seam_errors_v1"],
                        "human_message_v1": "RM preflight: " + "; ".join(seam_errs[:12]),
                        "memory_sink_event_count_v1": len(sink),
                        "preflight_seam_audit_v1": seam,
                    },
                )

            phase_holder["v"] = "trace_validation"
            _preflight_telemetry_update_v1(
                panel,
                phase="trace_validation",
                t0=t0,
                bars_replay_cap=bars_cap,
                bars_processed=int(_bars_proc)
                if isinstance(_bars_proc, (int, float)) and not isinstance(_bars_proc, bool)
                else None,
                note="memory_sink_rm_stages",
            )
            _emit_rm_preflight_panel_v1(panel, progress_cb)
            det = validate_rm_preflight_memory_sink_detailed_v1(
                sink,
                scenario_id=scenario_id,
                trade_id=trade_id,
                job_id=str(job_id).strip(),
            )
            ok_ev = bool(det.get("ok_v1"))
            missing = list(det.get("missing_stages_v1") or [])
            panel["preflight_sink_detail_v1"] = det
            st["job_id_bound_trace_v1"] = bool(det.get("job_id_binding_ok_v1"))
            st["breadcrumbs_validated_v1"] = ok_ev
            _emit_rm_preflight_panel_v1(panel, progress_cb)

            jbind_ok = _rm_preflight_job_binding_audit_v1(
                job_id=str(job_id).strip(),
                batch_first_scenario_id_v1=str(expected_batch_scenario_id_v1),
                worker_row_scenario_id_v1=str(row_sid),
                trade_id_v1=trade_id,
                scenario_binding_ok_v1=True,
                trace_job_binding_ok_v1=ok_ev,
            )
            if not ok_ev:
                st["terminal_pass_v1"] = False
                panel["failure_reasons_display_v1"] = map_rm_preflight_missing_to_operator_display_v1(missing)
                _emit_rm_preflight_panel_v1(panel, progress_cb)
                return _merge_panel_into_audit_v1(
                    panel,
                    {
                        "schema": "rm_preflight_wiring_audit_v1",
                        "ok_v1": False,
                        "skipped_v1": False,
                        "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                        "missing_stages_v1": missing,
                        "human_message_v1": "RM preflight: incomplete reasoning trace or job not bound to trace — "
                        + ", ".join(missing),
                        "memory_sink_event_count_v1": len(sink),
                        "preflight_seam_audit_v1": seam,
                        "preflight_trace_events_sample_v1": sink[n_sink_before_seam:][:40],
                        "rm_preflight_job_binding_audit_v1": jbind_ok,
                    },
                )

            st["terminal_pass_v1"] = True
            panel["failure_reasons_display_v1"] = []
            _emit_rm_preflight_panel_v1(panel, progress_cb)
            return _merge_panel_into_audit_v1(
                panel,
                {
                    "schema": "rm_preflight_wiring_audit_v1",
                    "ok_v1": True,
                    "skipped_v1": False,
                    "status_v1": "passed_rm_preflight_wiring_v1",
                    "missing_stages_v1": [],
                    "memory_sink_event_count_v1": len(sink),
                    "preflight_seam_audit_v1": seam,
                    "preflight_trade_id_v1": trade_id,
                    "preflight_scenario_id_v1": scenario_id,
                    "rm_preflight_job_binding_audit_v1": jbind_ok,
                    "preflight_replay_bounds_v1": {
                        "schema": "rm_preflight_replay_bounds_v1",
                        "calendar_months_v1": (shrunk.get("evaluation_window") or {}).get("calendar_months"),
                        "rm_preflight_replay_tail_bars_v1": shrunk.get("rm_preflight_replay_tail_bars_v1"),
                    },
                },
            )


        finally:
            hb_done.set()
            _hb_t.join(timeout=3.0)
__all__ = [
    "FAILED_PREFLIGHT_STATUS_V1",
    "REQUIRED_RM_PREFLIGHT_STAGES_V1",
    "rm_preflight_enabled_v1",
    "run_rm_preflight_wiring_v1",
    "should_skip_rm_preflight_v1",
    "validate_rm_preflight_memory_sink_v1",
]
