"""
RM preflight — in-memory wiring validation before parallel batch (Directive: reasoning_model).

* Shrinks the evaluation calendar window (default **1** month; ``PATTERN_GAME_RM_PREFLIGHT_MAX_CALENDAR_MONTHS``).
* **Decision-snapshot path (non-baseline Student):** builds ``student_decision_packet_v1`` from SQLite + manifest,
  runs ``run_entry_reasoning_pipeline_preflight_v1`` (tail-capped bars, router local-only) → authority →
  deterministic stub seal — **no** Referee replay worker
  and **no** wait for closed trades. In-process mode still uses ``PATTERN_GAME_RM_PREFLIGHT_DECISION_SNAPSHOT_TIMEOUT_S``
  (default **30**; fail ``preflight_timeout_decision_snapshot_v1``) as a monotonic inner deadline.
  Entry reasoning uses a tail slice (``PATTERN_GAME_RM_PREFLIGHT_ENTRY_MAX_BARS``, default **64**).
* **Hard wall (default on):** decision-snapshot preflight runs in a **spawn** subprocess and the parent
  ``terminate()``/``kill()`` the child if ``time.time()`` exceeds ``PATTERN_GAME_RM_PREFLIGHT_HARD_TIMEOUT_S``
  (when unset, defaults to **max(45s, decision-snapshot budget)** so the outer wall is not tighter than inner).
  Failure code: ``preflight_hard_timeout_v1``. Set
  ``PATTERN_GAME_RM_PREFLIGHT_SUBPROCESS_ISOLATION=0`` for in-process mode (e.g. tests that patch the snapshot).
* Bounded replay + ``_worker_run_one`` remain available for full exam / grading flows elsewhere; preflight does
  not depend on them.
* Validates required RM trace stages in the sink — **no** ``learning_trace_events_v1.jsonl`` writes.

Baseline may disable with ``PATTERN_GAME_RM_PREFLIGHT=0``. Non-baseline Student runs cannot
skip RM preflight via env (contract).
"""

from __future__ import annotations

import copy
import multiprocessing
import os
import queue
import sqlite3
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.candle_timeframe_runtime import extract_candle_timeframe_minutes_for_replay
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    normalize_student_reasoning_mode_v1,
)
from renaissance_v4.game_theory.groundhog_memory import resolve_memory_bundle_for_scenario
from renaissance_v4.game_theory.learning_trace_events_v1 import learning_trace_memory_sink_session_v1
from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
    emit_candle_timeframe_nexus_v1,
    emit_referee_used_student_output_batch_truth_v1,
    emit_student_output_sealed_v1,
    emit_student_reasoning_fault_map_v1,
    fingerprint_for_parallel_job_v1,
)
from renaissance_v4.game_theory.parallel_runner import _normalize_scenario
from renaissance_v4.game_theory.pattern_game import prepare_effective_manifest_for_replay
from renaissance_v4.game_theory.rm_preflight_context_v1 import (
    rm_preflight_early_exit_after_seal_active_v1,
    rm_preflight_seam_early_exit_session_v1,
)
from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    THESIS_REQUIRED_FOR_LLM_PROFILE_V1,
    validate_student_output_directional_thesis_required_for_llm_profile_v1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import (
    apply_engine_authority_to_student_output_v1,
    run_entry_reasoning_pipeline_preflight_v1,
)
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import emit_shadow_stub_student_output_v1
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    attach_student_context_annex_v1,
    build_student_context_annex_v1_from_entry_reasoning_eval_v1,
    build_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
    DECISION_SOURCE_REASONING_MODEL_V1,
    run_student_decision_authority_for_trade_v1,
    validate_student_decision_authority_mandate_preconditions_v1,
)
from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
    attach_fault_map_v1,
    merge_runtime_fault_nodes_v1,
)
from renaissance_v4.game_theory.student_rm_trace_contract_v1 import (
    student_rm_trace_mandate_begin_v1,
    student_rm_trace_mandate_reset_v1,
)
from renaissance_v4.manifest.validate import load_manifest_file
from renaissance_v4.utils.db import DB_PATH

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

# Decision-snapshot preflight (GT: no Referee closed trade / replay worker).
PREFLIGHT_DECISION_SNAPSHOT_TRADE_ID_V1 = "preflight_decision_snapshot_shell_v1"


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
    for _p in panel.get("preflight_snapshot_progress_v1") or []:
        lines.append(str(_p))

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
        if s.get("preflight_decision_snapshot_v1"):
            lines.append(
                f"RM PREFLIGHT TRADE BOUND — trade_id={tid!r} (decision snapshot shell; no replay trade) ✓"
            )
        else:
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
        elif s == "preflight_timeout_decision_snapshot_v1":
            out.append(
                "RM preflight decision-snapshot timeout — exceeded "
                "PATTERN_GAME_RM_PREFLIGHT_DECISION_SNAPSHOT_TIMEOUT_S"
            )
        elif s == "preflight_timeout_preflight_pipeline_v1":
            out.append(
                "RM preflight entry-reasoning SLA exceeded — exceeded "
                "PATTERN_GAME_RM_PREFLIGHT_PIPELINE_MAX_S (preflight pipeline only)"
            )
        elif s == "preflight_hard_timeout_v1":
            out.append(
                "RM preflight hard timeout — process terminated; exceeded "
                "PATTERN_GAME_RM_PREFLIGHT_HARD_TIMEOUT_S (wall clock, subprocess isolation)"
            )
        elif s == "preflight_decision_snapshot_subprocess_failed_v1":
            out.append("RM preflight subprocess failed (see human_message_v1)")
        else:
            out.append(s)
    return out


def _rm_preflight_decision_snapshot_timeout_s_v1() -> float:
    raw = (os.environ.get("PATTERN_GAME_RM_PREFLIGHT_DECISION_SNAPSHOT_TIMEOUT_S") or "30").strip()
    try:
        t = float(raw)
    except (TypeError, ValueError):
        t = 30.0
    return max(2.0, min(t, 30.0))


def _rm_preflight_hard_timeout_s_v1() -> float:
    """
    Wall-clock envelope for **entire** decision-snapshot preflight when subprocess isolation is on.
    When ``PATTERN_GAME_RM_PREFLIGHT_HARD_TIMEOUT_S`` is unset, defaults to at least **45s** and never
    below the decision-snapshot budget (subprocess overhead / SQLite / model cold start on lab hosts).
    """
    raw = (os.environ.get("PATTERN_GAME_RM_PREFLIGHT_HARD_TIMEOUT_S") or "").strip()
    if not raw:
        inner = float(_rm_preflight_decision_snapshot_timeout_s_v1())
        return max(45.0, inner)
    try:
        t = float(raw)
    except (TypeError, ValueError):
        return float(_rm_preflight_decision_snapshot_timeout_s_v1())
    return max(1.0, min(t, 120.0))


def _rm_preflight_subprocess_isolation_enabled_v1() -> bool:
    """When true (default), decision-snapshot preflight runs in a spawn child and is SIGKILL/terminate on SLA."""
    v = (os.environ.get("PATTERN_GAME_RM_PREFLIGHT_SUBPROCESS_ISOLATION") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


class _PreflightPhaseAuditCollectorV1:
    """Wall-clock + perf slices for RM preflight RCA (decision-snapshot path)."""

    def __init__(self, *, deadline_monotonic: float, budget_s_v1: float) -> None:
        self.deadline_monotonic = float(deadline_monotonic)
        self.budget_s_v1 = float(budget_s_v1)
        self.rows: list[dict[str, Any]] = []
        self._cur: str | None = None
        self._t0_perf: float = 0.0
        self._t0_wall_ms: int = 0

    def monotonic_over_deadline_v1(self) -> bool:
        return time.monotonic() > self.deadline_monotonic

    def open_phase_v1(self) -> str | None:
        return self._cur

    def enter(self, phase: str) -> None:
        self.end()
        self._cur = str(phase)
        self._t0_perf = time.perf_counter()
        self._t0_wall_ms = int(time.time() * 1000)

    def end(self, *, error: str | None = None, timeout_hit: bool = False) -> None:
        if self._cur is None:
            return
        t1p = time.perf_counter()
        t1w = int(time.time() * 1000)
        row: dict[str, Any] = {
            "phase": self._cur,
            "entered_v1": True,
            "started_at_ms_v1": int(self._t0_wall_ms),
            "ended_at_ms_v1": int(t1w),
            "elapsed_ms_v1": round((t1p - self._t0_perf) * 1000.0, 3),
            "timeout_hit_v1": bool(timeout_hit),
        }
        if error:
            row["error_v1"] = str(error)[:2000]
        self.rows.append(row)
        self._cur = None

    def append_skipped(self, phase: str, note_v1: str) -> None:
        self.rows.append(
            {
                "phase": str(phase),
                "entered_v1": False,
                "started_at_ms_v1": None,
                "ended_at_ms_v1": None,
                "elapsed_ms_v1": 0.0,
                "timeout_hit_v1": False,
                "note_v1": str(note_v1)[:500],
            }
        )

    def append_router_cost_rows_v1(self, *, unified_router_ran_v1: bool, bundle_wall_ms_v1: float | None) -> None:
        if not unified_router_ran_v1:
            self.append_skipped("reasoning_router_v1", "unified_agent_router_false_v1")
            self.append_skipped("reasoning_cost_governor_v1", "unified_agent_router_false_v1")
            return
        bms = float(bundle_wall_ms_v1) if isinstance(bundle_wall_ms_v1, (int, float)) else None
        tw = int(time.time() * 1000)
        base_note = (
            "wall_clock_inside_apply_unified_reasoning_router_v1 "
            "(router + cost governor emits occur in same call; see reasoning_router_bundle_wall_ms_v1 on ere)"
        )
        for ph in ("reasoning_router_v1", "reasoning_cost_governor_v1"):
            row: dict[str, Any] = {
                "phase": ph,
                "entered_v1": True,
                "started_at_ms_v1": None,
                "ended_at_ms_v1": int(tw),
                "elapsed_ms_v1": round(bms, 3) if bms is not None else None,
                "timeout_hit_v1": False,
                "note_v1": base_note,
            }
            self.rows.append(row)

    def snapshot_for_audit_v1(self, *, missing_stages_v1: list[str]) -> dict[str, Any]:
        root = _rm_preflight_root_cause_phase_v1(self.rows, missing_stages_v1=list(missing_stages_v1))
        return {
            "preflight_phase_audit_v1": list(self.rows),
            "root_cause_phase_v1": root,
            "preflight_decision_snapshot_budget_s_v1": float(self.budget_s_v1),
        }


def _rm_preflight_root_cause_phase_v1(
    rows: list[dict[str, Any]],
    *,
    missing_stages_v1: list[str],
) -> str:
    if not rows:
        return "preflight_unknown_no_phase_rows_v1"
    if "preflight_timeout_decision_snapshot_v1" in missing_stages_v1:
        for r in reversed(rows):
            if bool(r.get("timeout_hit_v1")):
                return str(r.get("phase") or "preflight_unknown_v1")
        for r in reversed(rows):
            if bool(r.get("entered_v1")) and r.get("ended_at_ms_v1") is None:
                return str(r.get("phase") or "preflight_unknown_v1")
        last = str(rows[-1].get("phase") or "preflight_unknown_v1")
        return f"preflight_timeout_inter_phase_v1:after_{last}"
    for r in reversed(rows):
        if r.get("error_v1"):
            return str(r.get("phase") or "preflight_unknown_v1")
    return str(rows[-1].get("phase") or "preflight_unknown_v1")


def _rm_preflight_merge_exam_lifecycle_into_packet_v1(
    pkt: dict[str, Any], ex_req: dict[str, Any] | None
) -> dict[str, Any]:
    """GT_DIRECTIVE_026B — same annex keys as the Student seam (no import cycle with operator runtime)."""
    if not isinstance(pkt, dict) or not isinstance(ex_req, dict):
        return pkt
    keys = (
        "bars_trade_lifecycle_inclusive_v1",
        "entry_bar_index_for_lifecycle_v1",
        "unified_agent_router_lifecycle_v1",
        "max_hold_bars_lifecycle_v1",
    )
    for k in keys:
        if ex_req.get(k) is None:
            continue
        v = ex_req[k]
        pkt[k] = copy.deepcopy(v) if k == "bars_trade_lifecycle_inclusive_v1" else v
    return pkt


def _rm_preflight_snapshot_progress_v1(panel: dict[str, Any], line: str) -> None:
    panel.setdefault("preflight_snapshot_progress_v1", []).append(str(line)[:400])


def _rm_preflight_symbol_from_manifest_v1(manifest: dict[str, Any]) -> str:
    sym = str(manifest.get("symbol") or "").strip()
    if sym:
        return sym
    return str(manifest.get("strategy_id") or "").strip()


def _rm_preflight_query_symbol_and_cut_ms_v1(
    db_path: Path, symbol_hint: str
) -> tuple[str | None, int | None, str | None]:
    """Return (symbol, decision_open_time_ms, error)."""
    try:
        conn = sqlite3.connect(str(db_path))
    except OSError as e:
        return None, None, f"sqlite_open_failed:{e}"
    try:
        cur = conn.cursor()
        sym = symbol_hint
        if not sym:
            row = cur.execute(
                "SELECT symbol FROM market_bars_5m WHERE symbol IS NOT NULL AND TRIM(symbol) != '' "
                "GROUP BY symbol ORDER BY COUNT(*) DESC LIMIT 1"
            ).fetchone()
            if not row or not row[0]:
                return None, None, "no_symbol_in_manifest_or_db"
            sym = str(row[0]).strip()
        mx = cur.execute(
            "SELECT MAX(open_time) FROM market_bars_5m WHERE symbol = ?",
            (sym,),
        ).fetchone()
        if not mx or mx[0] is None:
            return sym, None, f"no_bars_for_symbol:{sym}"
        return sym, int(mx[0]), None
    finally:
        conn.close()


def _rm_preflight_augment_stub_for_llm_thesis_v1(
    so: dict[str, Any],
    *,
    ere: dict[str, Any],
    pkt: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic §1.0 thesis fields for preflight only (no Ollama); packet/ERE-derived."""
    out = copy.deepcopy(so)
    ictx = (ere.get("indicator_context_eval_v1") or {}) if isinstance(ere, dict) else {}
    rsi = str(ictx.get("rsi_state") or "unknown")
    ema = str(ictx.get("ema_trend") or "unknown")
    sym = str(pkt.get("symbol") or "")
    nbar = len(pkt.get("bars_inclusive_up_to_t") or []) if isinstance(pkt.get("bars_inclusive_up_to_t"), list) else 0
    risk = (ere.get("risk_inputs_v1") or {}) if isinstance(ere, dict) else {}
    inv = str(risk.get("invalidation_condition_v1") or "invalidation per packet risk_inputs_v1")
    ds = (ere.get("decision_synthesis_v1") or {}) if isinstance(ere, dict) else {}
    act = str(ds.get("action") or "no_trade")
    band = str(ere.get("confidence_band") or "medium")
    out["context_interpretation_v1"] = (
        f"Preflight snapshot: {sym} causal window ({nbar} bars), RSI={rsi}, EMA trend={ema}. "
        f"Engine synthesis action={act}."
    )
    out["hypothesis_kind_v1"] = "trend_continuation"
    out["hypothesis_text_v1"] = f"Preflight wiring check aligned with engine action {act} on {sym}."
    out["supporting_indicators"] = [f"ema_trend:{ema}", f"rsi_state:{rsi}"]
    out["conflicting_indicators"] = [f"engine_action_anchor:{act}"]
    out["confidence_band"] = band if band in ("low", "medium", "high") else "medium"
    out["context_fit"] = "preflight_rm_chain_ok_v1"
    out["invalidation_text"] = inv[:500] if len(inv) > 500 else inv
    sa = str(out.get("student_action_v1") or "").strip().lower()
    if sa not in ("enter_long", "enter_short", "no_trade"):
        ds_act = act if act in ("enter_long", "enter_short", "no_trade") else "no_trade"
        out["student_action_v1"] = ds_act
    return out


def run_rm_preflight_decision_snapshot_v1(
    *,
    scenario: dict[str, Any],
    job_id: str,
    exam_run_contract_request_v1: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    panel: dict[str, Any],
    cancel_check: Callable[[], bool] | None,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    t0: float,
    deadline: float,
) -> dict[str, Any]:
    """
    Build causal packet → entry reasoning (+ unified router when mandated) → authority → stub seal
    with RM trace emits. Returns audit fragment for ``run_rm_preflight_wiring_v1`` merge.

    On failure: ``ok_v1`` False, ``missing_stages_v1`` / ``human_message_v1`` populated, plus
    ``preflight_phase_audit_v1`` / ``root_cause_phase_v1`` for RCA.
    """
    st = panel.setdefault("stages_v1", {})
    st["preflight_decision_snapshot_v1"] = True
    jid = str(job_id).strip()
    ex_req = exam_run_contract_request_v1 if isinstance(exam_run_contract_request_v1, dict) else None
    oba = operator_batch_audit if isinstance(operator_batch_audit, dict) else None
    scenario_id = str(scenario.get("scenario_id") or "unknown").strip()
    trade_id = PREFLIGHT_DECISION_SNAPSHOT_TRADE_ID_V1
    budget_s_v1 = float(_rm_preflight_decision_snapshot_timeout_s_v1())
    audit = _PreflightPhaseAuditCollectorV1(deadline_monotonic=float(deadline), budget_s_v1=budget_s_v1)

    def _timeout() -> bool:
        return time.monotonic() > float(deadline)

    def _fail(
        *,
        missing: list[str],
        human: str,
        seam_audit: dict[str, Any] | None = None,
        timeout_on_open_phase_v1: bool = False,
    ) -> dict[str, Any]:
        if timeout_on_open_phase_v1 and audit.open_phase_v1() is not None:
            audit.end(timeout_hit=True, error="preflight_deadline_monotonic_exceeded_v1")
        else:
            audit.end()
        snap = audit.snapshot_for_audit_v1(missing_stages_v1=list(missing))
        panel["preflight_phase_audit_v1"] = snap.get("preflight_phase_audit_v1")
        panel["root_cause_phase_v1"] = snap.get("root_cause_phase_v1")
        panel["preflight_decision_snapshot_budget_s_v1"] = snap.get("preflight_decision_snapshot_budget_s_v1")
        st["terminal_pass_v1"] = False
        panel["failure_reasons_display_v1"] = map_rm_preflight_missing_to_operator_display_v1(missing)
        if human and human not in panel["failure_reasons_display_v1"]:
            panel["failure_reasons_display_v1"] = [human] + list(panel["failure_reasons_display_v1"])
        _emit_rm_preflight_panel_v1(panel, progress_cb)
        return {
            "ok_v1": False,
            "scenario_id": scenario_id,
            "trade_id": trade_id,
            "seam_audit": seam_audit,
            "missing_stages_v1": missing,
            "human_message_v1": human,
            **snap,
        }

    if _preflight_cancel_hit_v1(cancel_check):
        return _fail(missing=["cancelled_during_preflight_v1"], human="cancelled")

    if _timeout():
        audit.append_skipped(
            "preflight_budget_exhausted_before_snapshot_v1",
            "monotonic_deadline_exceeded_before_snapshot_build_v1",
        )
        return _fail(
            missing=["preflight_timeout_decision_snapshot_v1"],
            human="preflight_timeout_decision_snapshot_v1",
            timeout_on_open_phase_v1=False,
        )

    profile = normalize_student_reasoning_mode_v1(
        str((ex_req or {}).get("student_brain_profile_v1") or (ex_req or {}).get("student_reasoning_mode") or "")
    )
    use_llm = profile == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1

    # Preflight uses a deterministic stub seal (no Ollama round-trip); do not block on LLM gate here.
    # The full Student seam after the parallel batch still enforces LLM resolution for real trades.
    _mandate_pre = validate_student_decision_authority_mandate_preconditions_v1(
        exam_run_contract_request_v1=ex_req,
        job_id=jid,
        student_brain_profile_v1=profile,
        student_llm_gate_blocked_batch_v1=False,
    )
    if _mandate_pre:
        return _fail(
            missing=["student_decision_authority_mandate_preconditions_failed_v1"],
            human="; ".join(str(x) for x in _mandate_pre[:12]),
            seam_audit={
                "schema": "student_loop_seam_audit_v1",
                "skipped": True,
                "reason": "student_decision_authority_mandate_preconditions_failed_v1",
                "student_decision_authority_mandate_errors_v1": list(_mandate_pre),
            },
        )

    mbp = scenario.get("memory_bundle_path")
    if mbp:
        mbp = str(Path(str(mbp)).expanduser().resolve())
    else:
        mbp = resolve_memory_bundle_for_scenario(scenario, explicit_path=None)

    prep = None
    audit.enter("snapshot_build_v1")
    try:
        prep = prepare_effective_manifest_for_replay(
            scenario["manifest_path"],
            atr_stop_mult=scenario.get("atr_stop_mult"),
            atr_target_mult=scenario.get("atr_target_mult"),
            memory_bundle_path=mbp,
            use_groundhog_auto_resolve=False,
        )
        manifest = load_manifest_file(prep.replay_path)
    except Exception as e:
        audit.end(error=f"{type(e).__name__}: {e}")
        if prep is not None:
            try:
                prep.cleanup()
            except Exception:
                pass
        return _fail(
            missing=["preflight_manifest_prepare_failed_v1"],
            human=f"{type(e).__name__}: {e}",
        )

    mandate_tok = None
    try:
        if _timeout():
            audit.end(timeout_hit=True, error="deadline_before_sqlite_slice_v1")
            return _fail(
                missing=["preflight_timeout_decision_snapshot_v1"],
                human="preflight_timeout_decision_snapshot_v1",
                timeout_on_open_phase_v1=False,
            )
        sym_hint = _rm_preflight_symbol_from_manifest_v1(manifest)
        db_used = Path(str(DB_PATH)).resolve()
        sym_res, cut_ms, qerr = _rm_preflight_query_symbol_and_cut_ms_v1(db_used, sym_hint)
        if qerr or not sym_res or cut_ms is None:
            audit.end(error=str(qerr or "no_market_slice"))
            return _fail(
                missing=["preflight_decision_snapshot_no_market_slice_v1"],
                human=qerr or "preflight_decision_snapshot_no_market_slice_v1",
            )

        c_tf = extract_candle_timeframe_minutes_for_replay(scenario)
        for cand in ((ex_req or {}).get("candle_timeframe_minutes"), (oba or {}).get("candle_timeframe_minutes")):
            if cand is not None:
                try:
                    t = int(cand)
                    if t in (5, 15, 60, 240):
                        c_tf = t
                        break
                except (TypeError, ValueError):
                    pass

        pkt, perr = build_student_decision_packet_v1(
            db_path=db_used,
            symbol=sym_res,
            decision_open_time_ms=cut_ms,
            candle_timeframe_minutes=int(c_tf),
            notes="rm_preflight_decision_snapshot_v1",
        )
        if perr or pkt is None:
            audit.end(error=str(perr or "packet_none"))
            return _fail(
                missing=["preflight_decision_snapshot_packet_failed_v1"],
                human=str(perr or "packet_none"),
            )
        pkt = _rm_preflight_merge_exam_lifecycle_into_packet_v1(pkt, ex_req)
        audit.end()

        _rm_preflight_snapshot_progress_v1(panel, "snapshot_loaded")
        _emit_rm_preflight_panel_v1(panel, progress_cb)

        scorecard_entry_effective = find_scorecard_entry_by_job_id(jid)
        fp_emit = fingerprint_for_parallel_job_v1(
            operator_batch_audit=oba if oba else None,
            fingerprint_preview=None,
            scorecard_line=scorecard_entry_effective if isinstance(scorecard_entry_effective, dict) else None,
        )

        mandate_active_v1 = profile != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1
        unified_router = bool(mandate_active_v1)

        if mandate_active_v1:
            mandate_tok = student_rm_trace_mandate_begin_v1()
        try:
            emit_candle_timeframe_nexus_v1(
                job_id=jid,
                fingerprint=fp_emit,
                nexus="run_contract",
                candle_timeframe_minutes=int(c_tf),
            )
            emit_candle_timeframe_nexus_v1(
                job_id=jid,
                fingerprint=fp_emit,
                nexus="student_packet",
                candle_timeframe_minutes=int(c_tf),
                scenario_id=scenario_id,
                trade_id=trade_id,
            )

            if _timeout():
                audit.enter("rm_entry_reasoning_v1")
                audit.end(timeout_hit=True, error="deadline_before_run_entry_reasoning_pipeline_v1_after_nexus")
                return _fail(
                    missing=["preflight_timeout_decision_snapshot_v1"],
                    human="preflight_timeout_decision_snapshot_v1",
                    timeout_on_open_phase_v1=False,
                )

            rxx: list[dict[str, Any]] = []
            _rm_preflight_snapshot_progress_v1(panel, "rm_invoked")
            _emit_rm_preflight_panel_v1(panel, progress_cb)

            audit.enter("rm_entry_reasoning_v1")
            ere, ere_err, _trace, pfm = run_entry_reasoning_pipeline_preflight_v1(
                student_decision_packet=pkt,
                retrieved_student_experience=rxx,
                run_candle_timeframe_minutes=int(c_tf),
                job_id=jid,
                fingerprint=fp_emit,
                scenario_id=scenario_id,
                trade_id=trade_id,
                emit_traces=True,
                unified_agent_router=unified_router,
            )
            if ere is None:
                audit.end(error="; ".join(ere_err) if ere_err else "entry_reasoning_none")
                miss = list(ere_err or [])
                if "preflight_timeout_preflight_pipeline_v1" in miss:
                    return _fail(
                        missing=["preflight_timeout_preflight_pipeline_v1"],
                        human="preflight_timeout_preflight_pipeline_v1",
                    )
                return _fail(
                    missing=["preflight_entry_reasoning_failed_v1"],
                    human="; ".join(ere_err) if ere_err else "entry_reasoning_none",
                )
            audit.end()

            if isinstance(ere, dict) and isinstance(pfm, dict):
                ere["student_reasoning_fault_map_v1"] = pfm

            _bundle_ms = ere.get("reasoning_router_bundle_wall_ms_v1") if isinstance(ere, dict) else None
            audit.append_skipped(
                "llm_inference_v1",
                "preflight_stub_seal_v1_no_live_ollama_rca: seam_after_replay_calls_emit_student_output_via_ollama_v1",
            )
            audit.append_router_cost_rows_v1(
                unified_router_ran_v1=bool(unified_router),
                bundle_wall_ms_v1=float(_bundle_ms) if isinstance(_bundle_ms, (int, float)) else None,
            )

            if isinstance(ere, dict):
                _ann_pf = build_student_context_annex_v1_from_entry_reasoning_eval_v1(ere)
                _pkt_pf, _aerr_pf = attach_student_context_annex_v1(pkt, _ann_pf)
                if _pkt_pf is not None:
                    pkt = _pkt_pf

            audit.enter("output_seal_v1")
            so, soe = emit_shadow_stub_student_output_v1(
                pkt,
                graded_unit_id=trade_id,
                decision_at_ms=cut_ms,
            )
            if soe or so is None:
                audit.end(error="; ".join(soe) if soe else "stub_none")
                return _fail(
                    missing=["preflight_shadow_stub_failed_v1"],
                    human="; ".join(soe) if soe else "stub_none",
                )

            audit.enter("student_decision_authority_v1")
            run_student_decision_authority_for_trade_v1(
                job_id=jid,
                fingerprint=fp_emit,
                scenario_id=scenario_id,
                trade_id=trade_id,
                ere=ere,
                pkt=pkt,
                unified_router_enabled=unified_router,
                exam_run_contract_request_v1=ex_req,
                mandate_active_v1=mandate_active_v1,
            )
            audit.end()

            so, auth_errs = apply_engine_authority_to_student_output_v1(
                so,
                ere,
                allowed_memory_ids=frozenset(),
            )
            if so is None or auth_errs:
                audit.end(error="; ".join(auth_errs) if auth_errs else "null_student_output")
                return _fail(
                    missing=["preflight_engine_authority_merge_failed_v1"],
                    human="; ".join(auth_errs) if auth_errs else "null_student_output",
                )

            if use_llm:
                so = _rm_preflight_augment_stub_for_llm_thesis_v1(so, ere=ere, pkt=pkt)
                v0 = validate_student_output_v1(so)
                if v0:
                    audit.end(error="; ".join(v0)[:2000])
                    return _fail(
                        missing=["preflight_llm_thesis_shape_failed_v1"],
                        human="; ".join(v0)[:2000],
                    )
                te = validate_student_output_directional_thesis_required_for_llm_profile_v1(so)
                if te:
                    audit.end(error="; ".join(te)[:2000])
                    return _fail(
                        missing=["preflight_llm_thesis_shape_failed_v1"],
                        human="; ".join(te)[:2000],
                    )

            if mandate_active_v1:
                _bind = ere.get("student_decision_authority_binding_v1") if isinstance(ere, dict) else None
                if not isinstance(_bind, dict) or not _bind.get("learning_trace_persisted_v1"):
                    return _fail(
                        missing=["student_decision_authority_mandate_binding_missing_v1"],
                        human="STUDENT_DECISION_AUTHORITY_MANDATE_V1: binding missing after authority",
                    )
                if isinstance(so, dict) and isinstance(_bind, dict) and _bind.get("decision_source_v1"):
                    so["decision_source_v1"] = str(_bind["decision_source_v1"])

            ulm = False
            _full_fm = merge_runtime_fault_nodes_v1(
                pfm if isinstance(pfm, dict) else {},
                use_llm_path=ulm,
                llm_checked_pass=bool(ulm),
                llm_error_codes=[],
                llm_operator_message="",
                student_sealed_pass=True,
                student_seal_error_codes=[],
                student_seal_message="Preflight decision-snapshot seal (no full reveal path).",
                execution_intent_pass=True,
                execution_intent_error_codes=[],
                execution_intent_message="Preflight wiring only.",
            )
            attach_fault_map_v1(so, _full_fm)
            emit_student_reasoning_fault_map_v1(
                job_id=jid,
                fingerprint=fp_emit,
                scenario_id=scenario_id,
                trade_id=trade_id,
                student_reasoning_fault_map_v1=so.get("student_reasoning_fault_map_v1")
                if isinstance(so, dict)
                else None,
            )

            via = "preflight_decision_snapshot_stub_v1"
            protocol_extras: dict[str, Any]
            if use_llm:
                te_snap = validate_student_output_directional_thesis_required_for_llm_profile_v1(so)
                protocol_extras = {
                    "student_decision_protocol_ok_v1": len(te_snap) == 0,
                    "student_decision_protocol_errors_v1": te_snap[:20],
                    "student_decision_protocol_keys_expected_v1": list(THESIS_REQUIRED_FOR_LLM_PROFILE_V1),
                }
            else:
                protocol_extras = {
                    "student_decision_protocol_ok_v1": True,
                    "student_decision_protocol_errors_v1": [],
                    "student_decision_protocol_keys_expected_v1": [],
                }

            emit_student_output_sealed_v1(
                job_id=jid,
                fingerprint=fp_emit,
                scenario_id=scenario_id,
                trade_id=trade_id,
                via=via,
                decision_source_v1=str(so.get("decision_source_v1") or "").strip() or None,
                student_action_v1_echo=str(so.get("student_action_v1") or "").strip() or None,
                decision_protocol_extras_v1=protocol_extras,
            )
            audit.end()
            audit.append_skipped(
                "protocol_validation_v1",
                "student_output_schema_and_thesis_checks_ran_inside_output_seal_v1_elapsed_ms_v1",
            )

            if rm_preflight_early_exit_after_seal_active_v1():
                emit_referee_used_student_output_batch_truth_v1(
                    job_id=jid,
                    fingerprint=fp_emit,
                    student_influence_on_worker_replay_v1="false",
                    detail=(
                        "rm_preflight_decision_snapshot_v1: sealed Student line validated without "
                        "Referee replay worker or closed-trade dependency."
                    ),
                )

            _rm_preflight_snapshot_progress_v1(panel, "breadcrumbs_emitted")
            _emit_rm_preflight_panel_v1(panel, progress_cb)

            if _timeout():
                audit.enter("preflight_post_seal_v1")
                audit.end(timeout_hit=True, error="deadline_after_student_output_sealed_emit_v1")
                return _fail(
                    missing=["preflight_timeout_decision_snapshot_v1"],
                    human="preflight_timeout_decision_snapshot_v1",
                    timeout_on_open_phase_v1=False,
                )

            seam_audit = {
                "schema": "student_loop_seam_audit_v1",
                "run_id": jid,
                "rm_preflight_wiring_early_exit_v1": True,
                "preflight_path_v1": "decision_snapshot_v1",
                "preflight_worker_replay_invoked_v1": False,
                "preflight_referee_replay_invoked_v1": False,
                "trades_considered": 1,
                "errors": [],
                "student_emit_occurred": True,
            }
            ok_snap = audit.snapshot_for_audit_v1(missing_stages_v1=[])
            panel["preflight_phase_audit_v1"] = ok_snap.get("preflight_phase_audit_v1")
            panel["preflight_decision_snapshot_budget_s_v1"] = ok_snap.get("preflight_decision_snapshot_budget_s_v1")
            return {
                "ok_v1": True,
                "scenario_id": scenario_id,
                "trade_id": trade_id,
                "seam_audit": seam_audit,
                "missing_stages_v1": [],
                "human_message_v1": None,
                "preflight_phase_audit_v1": ok_snap.get("preflight_phase_audit_v1"),
                "root_cause_phase_v1": None,
                "preflight_decision_snapshot_budget_s_v1": ok_snap.get("preflight_decision_snapshot_budget_s_v1"),
            }
        finally:
            if mandate_tok is not None:
                try:
                    student_rm_trace_mandate_reset_v1(mandate_tok)
                except Exception:
                    pass
    finally:
        try:
            prep.cleanup()
        except Exception:
            pass


def _rm_preflight_decision_snapshot_subprocess_entry_v1(
    result_q: Any,
    payload: dict[str, Any],
) -> None:
    """Spawn entrypoint — isolated interpreter; must stay top-level for pickling."""
    try:
        ddl_wall = float(payload["deadline_wall_time"])
        rem = ddl_wall - time.time()
        mono_deadline = time.monotonic() + max(0.05, rem)
        t0 = time.monotonic()
        jid = str(payload.get("job_id") or "").strip()
        with learning_trace_memory_sink_session_v1() as sink:
            with rm_preflight_seam_early_exit_session_v1():
                panel = _new_rm_preflight_results_panel_v1(jid)
                branch = run_rm_preflight_decision_snapshot_v1(
                    scenario=payload["scenario"],
                    job_id=jid,
                    exam_run_contract_request_v1=payload.get("exam_run_contract_request_v1"),
                    operator_batch_audit=payload.get("operator_batch_audit"),
                    panel=panel,
                    cancel_check=None,
                    progress_cb=None,
                    t0=t0,
                    deadline=mono_deadline,
                )
        result_q.put(
            {
                "kind": "done",
                "branch": copy.deepcopy(branch),
                "sink": copy.deepcopy(sink),
                "panel": copy.deepcopy(panel),
            }
        )
    except Exception as e:
        try:
            result_q.put({"kind": "error", "message": f"{type(e).__name__}: {e}"})
        except Exception:
            pass


def _rm_preflight_run_decision_snapshot_isolated_v1(
    *,
    scenario: dict[str, Any],
    job_id: str,
    exam_run_contract_request_v1: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    cancel_check: Callable[[], bool] | None,
    hard_timeout_s: float,
) -> dict[str, Any]:
    """
    Run decision-snapshot preflight in a **spawn** subprocess; ``terminate()``/``kill()`` on SLA breach.

    ``cancel_check`` is polled in the parent only (child has no cancel callback).
    ``progress_cb`` is not invoked in the child (use telemetry after merge).
    """
    ctx = multiprocessing.get_context("spawn")
    result_q: multiprocessing.Queue = ctx.Queue(maxsize=2)
    deadline_wall = time.time() + float(hard_timeout_s)
    payload: dict[str, Any] = {
        "scenario": scenario,
        "job_id": str(job_id).strip(),
        "exam_run_contract_request_v1": exam_run_contract_request_v1,
        "operator_batch_audit": operator_batch_audit,
        "deadline_wall_time": deadline_wall,
    }
    # Resolve at call time so tests may monkeypatch ``_rm_preflight_decision_snapshot_subprocess_entry_v1``.
    import renaissance_v4.game_theory.rm_preflight_wiring_v1 as _rmw_self

    _entry = getattr(_rmw_self, "_rm_preflight_decision_snapshot_subprocess_entry_v1")
    proc = ctx.Process(
        target=_entry,
        args=(result_q, payload),
        name="rm_preflight_decision_snapshot_v1",
        daemon=True,
    )
    proc.start()
    try:
        while proc.is_alive():
            if time.time() >= deadline_wall:
                proc.terminate()
                proc.join(timeout=3.0)
                if proc.is_alive():
                    proc.kill()
                    proc.join(timeout=2.0)
                return {"mode": "hard_timeout"}
            if _preflight_cancel_hit_v1(cancel_check):
                proc.terminate()
                proc.join(timeout=3.0)
                if proc.is_alive():
                    proc.kill()
                    proc.join(timeout=2.0)
                return {"mode": "cancelled"}
            proc.join(timeout=0.05)
        proc.join(timeout=1.0)
        if proc.exitcode not in (0, None):
            return {"mode": "error", "message": f"child_exit:{proc.exitcode}"}
        try:
            item = result_q.get(timeout=30.0)
        except queue.Empty:
            return {"mode": "error", "message": "no_result_from_child_queue"}
        if not isinstance(item, dict):
            return {"mode": "error", "message": "invalid_child_payload"}
        if item.get("kind") == "done":
            return {
                "mode": "ok",
                "branch": item.get("branch"),
                "sink": item.get("sink"),
                "panel": item.get("panel"),
            }
        if item.get("kind") == "error":
            return {"mode": "error", "message": str(item.get("message") or "child_error")}
        return {"mode": "error", "message": "unknown_child_kind"}
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1.0)
            if proc.is_alive():
                try:
                    proc.kill()
                except Exception:
                    pass
                proc.join(timeout=1.0)


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
        hard_s = float(_rm_preflight_hard_timeout_s_v1())
        use_iso = _rm_preflight_subprocess_isolation_enabled_v1()
        _preflight_telemetry_update_v1(
            panel,
            phase="decision_snapshot_v1",
            t0=t0,
            bars_replay_cap=bars_cap,
            heartbeat_seq=0,
            note=(
                "rm_preflight_decision_snapshot_subprocess_spawn_v1"
                if use_iso
                else "rm_preflight_decision_snapshot_no_replay_worker_v1"
            ),
        )
        _emit_rm_preflight_panel_v1(panel, progress_cb)
        branch: dict[str, Any]
        sink_events: list[dict[str, Any]] = []
        try:
            if use_iso:
                iso = _rm_preflight_run_decision_snapshot_isolated_v1(
                    scenario=shrunk,
                    job_id=str(job_id).strip(),
                    exam_run_contract_request_v1=exam_run_contract_request_v1,
                    operator_batch_audit=operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
                    cancel_check=cancel_check,
                    hard_timeout_s=hard_s,
                )
                if iso.get("mode") == "hard_timeout":
                    st["terminal_pass_v1"] = False
                    panel["preflight_hard_timeout_v1"] = True
                    panel["failure_reasons_display_v1"] = map_rm_preflight_missing_to_operator_display_v1(
                        ["preflight_hard_timeout_v1"]
                    )
                    _emit_rm_preflight_panel_v1(panel, progress_cb)
                    return _merge_panel_into_audit_v1(
                        panel,
                        {
                            "schema": "rm_preflight_wiring_audit_v1",
                            "ok_v1": False,
                            "skipped_v1": False,
                            "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                            "missing_stages_v1": ["preflight_hard_timeout_v1"],
                            "human_message_v1": "preflight_hard_timeout_v1",
                            "memory_sink_event_count_v1": 0,
                        },
                    )
                if iso.get("mode") == "cancelled":
                    st["terminal_pass_v1"] = False
                    panel["failure_reasons_display_v1"] = ["cancelled_during_preflight_v1"]
                    _emit_rm_preflight_panel_v1(panel, progress_cb)
                    return _merge_panel_into_audit_v1(
                        panel,
                        _operator_cancelled_preflight_audit_v1(memory_sink_event_count_v1=0),
                    )
                if iso.get("mode") != "ok":
                    st["terminal_pass_v1"] = False
                    em = str(iso.get("message") or "preflight_decision_snapshot_subprocess_failed_v1")
                    panel["failure_reasons_display_v1"] = [em]
                    _emit_rm_preflight_panel_v1(panel, progress_cb)
                    return _merge_panel_into_audit_v1(
                        panel,
                        {
                            "schema": "rm_preflight_wiring_audit_v1",
                            "ok_v1": False,
                            "skipped_v1": False,
                            "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                            "missing_stages_v1": ["preflight_decision_snapshot_subprocess_failed_v1"],
                            "human_message_v1": em,
                            "memory_sink_event_count_v1": 0,
                        },
                    )
                br = iso.get("branch")
                branch = br if isinstance(br, dict) else {}
                pnl = iso.get("panel")
                if isinstance(pnl, dict):
                    panel.clear()
                    panel.update(pnl)
                sk = iso.get("sink")
                sink_events = list(sk) if isinstance(sk, list) else []
            else:
                deadline = t0 + float(_rm_preflight_decision_snapshot_timeout_s_v1())
                with rm_preflight_seam_early_exit_session_v1():
                    branch = run_rm_preflight_decision_snapshot_v1(
                        scenario=shrunk,
                        job_id=str(job_id).strip(),
                        exam_run_contract_request_v1=exam_run_contract_request_v1,
                        operator_batch_audit=operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
                        panel=panel,
                        cancel_check=cancel_check,
                        progress_cb=progress_cb,
                        t0=t0,
                        deadline=deadline,
                    )
                sink_events = list(sink)
        except Exception as e:
            st["terminal_pass_v1"] = False
            panel["failure_reasons_display_v1"] = [f"preflight_decision_snapshot_exception_v1: {e!r}"]
            _emit_rm_preflight_panel_v1(panel, progress_cb)
            return _merge_panel_into_audit_v1(
                panel,
                {
                    "schema": "rm_preflight_wiring_audit_v1",
                    "ok_v1": False,
                    "skipped_v1": False,
                    "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                    "missing_stages_v1": ["preflight_decision_snapshot_exception_v1"],
                    "human_message_v1": f"{type(e).__name__}: {e}",
                    "memory_sink_event_count_v1": len(sink),
                },
            )

        if not branch.get("ok_v1"):
            miss = list(branch.get("missing_stages_v1") or [])
            return _merge_panel_into_audit_v1(
                panel,
                {
                    "schema": "rm_preflight_wiring_audit_v1",
                    "ok_v1": False,
                    "skipped_v1": False,
                    "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                    "missing_stages_v1": miss,
                    "human_message_v1": str(branch.get("human_message_v1") or "rm_preflight_decision_snapshot_v1 failed"),
                    "memory_sink_event_count_v1": len(sink_events),
                    "preflight_seam_audit_v1": branch.get("seam_audit"),
                    "preflight_decision_snapshot_branch_v1": branch,
                },
            )

        expected_batch_scenario_id_v1 = str(shrunk.get("scenario_id") or "unknown").strip()
        scenario_id = str(branch.get("scenario_id") or "").strip()
        trade_id = str(branch.get("trade_id") or PREFLIGHT_DECISION_SNAPSHOT_TRADE_ID_V1).strip()
        seam = branch.get("seam_audit") if isinstance(branch.get("seam_audit"), dict) else {}

        if scenario_id != expected_batch_scenario_id_v1:
            st["scenario_bound_failed_v1"] = True
            st["terminal_pass_v1"] = False
            panel["failure_reasons_display_v1"] = map_rm_preflight_missing_to_operator_display_v1(
                ["job_binding_scenario_mismatch_v1"]
            )
            jbind = _rm_preflight_job_binding_audit_v1(
                job_id=str(job_id).strip(),
                batch_first_scenario_id_v1=str(expected_batch_scenario_id_v1),
                worker_row_scenario_id_v1=str(scenario_id),
                trade_id_v1=trade_id,
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
                        "RM preflight: decision snapshot scenario_id does not match first submitted scenario "
                        f"(batch_first={expected_batch_scenario_id_v1!r}, branch={scenario_id!r})."
                    ),
                    "memory_sink_event_count_v1": len(sink_events),
                    "rm_preflight_job_binding_audit_v1": jbind,
                },
            )

        st["scenario_bound_v1"] = True
        panel["active_scenario_id_v1"] = scenario_id
        st["trade_bound_v1"] = True
        panel["active_trade_id_v1"] = trade_id
        st["seam_completed_v1"] = True
        _emit_rm_preflight_panel_v1(panel, progress_cb)

        n_sink_before_validate = len(sink_events)
        _preflight_telemetry_update_v1(
            panel,
            phase="trace_validation",
            t0=t0,
            bars_replay_cap=bars_cap,
            bars_processed=None,
            note="memory_sink_rm_stages_decision_snapshot_v1",
        )
        _emit_rm_preflight_panel_v1(panel, progress_cb)
        det = validate_rm_preflight_memory_sink_detailed_v1(
            sink_events,
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
            worker_row_scenario_id_v1=str(scenario_id),
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
                    "memory_sink_event_count_v1": len(sink_events),
                    "preflight_seam_audit_v1": seam,
                    "preflight_trace_events_sample_v1": sink_events[n_sink_before_validate:][:40],
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
                "memory_sink_event_count_v1": len(sink_events),
                "preflight_seam_audit_v1": seam,
                "preflight_trade_id_v1": trade_id,
                "preflight_scenario_id_v1": scenario_id,
                "rm_preflight_job_binding_audit_v1": jbind_ok,
                "preflight_replay_bounds_v1": {
                    "schema": "rm_preflight_replay_bounds_v1",
                    "calendar_months_v1": (shrunk.get("evaluation_window") or {}).get("calendar_months"),
                    "rm_preflight_replay_tail_bars_v1": shrunk.get("rm_preflight_replay_tail_bars_v1"),
                    "preflight_path_v1": "decision_snapshot_v1",
                },
            },
        )
__all__ = [
    "FAILED_PREFLIGHT_STATUS_V1",
    "PREFLIGHT_DECISION_SNAPSHOT_TRADE_ID_V1",
    "REQUIRED_RM_PREFLIGHT_STAGES_V1",
    "rm_preflight_enabled_v1",
    "run_rm_preflight_decision_snapshot_v1",
    "run_rm_preflight_wiring_v1",
    "should_skip_rm_preflight_v1",
    "validate_rm_preflight_memory_sink_v1",
]
