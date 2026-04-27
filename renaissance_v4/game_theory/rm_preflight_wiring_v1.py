"""
RM preflight — bounded in-memory wiring validation before parallel batch (Directive: reasoning_model).

* Shrinks calendar window for **one** in-process worker row (same ``_worker_run_one`` as production).
* Runs **one** Student seam pass with memory trace sink + early exit after first ``student_output_sealed``.
* Validates required RM trace stages in the sink — **no** ``learning_trace_events_v1.jsonl`` writes.

Baseline may disable with ``PATTERN_GAME_RM_PREFLIGHT=0``. Non-baseline Student runs cannot
skip RM preflight via env (contract).
"""

from __future__ import annotations

import copy
import os
from collections import defaultdict
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
    s = copy.deepcopy(scenario)
    try:
        cap = int(os.environ.get("PATTERN_GAME_RM_PREFLIGHT_MAX_CALENDAR_MONTHS", "2"))
    except (TypeError, ValueError):
        cap = 2
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
    return s


def validate_rm_preflight_memory_sink_v1(
    events: list[dict[str, Any]],
    *,
    scenario_id: str,
    trade_id: str,
) -> tuple[bool, list[str]]:
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
    missing: list[str] = []
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
    return len(missing) == 0, sorted(set(missing))


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
) -> dict[str, Any]:
    """
    Returns ``ok_v1`` False on any failure (worker, seam, or missing trace stages).

    On success, ``skipped_v1`` may still be True when policy skips preflight.
    """
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
        return {
            "schema": "rm_preflight_wiring_audit_v1",
            "ok_v1": True,
            "skipped_v1": True,
            "skip_reason_v1": skip,
            "status_v1": None,
            "missing_stages_v1": [],
            "memory_sink_event_count_v1": 0,
        }
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
        row = _worker_run_one(shrunk)
        if not row.get("ok"):
            return {
                "schema": "rm_preflight_wiring_audit_v1",
                "ok_v1": False,
                "skipped_v1": False,
                "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                "missing_stages_v1": ["preflight_worker_row_failed_v1"],
                "human_message_v1": str(row.get("error") or "worker row not ok"),
                "memory_sink_event_count_v1": len(sink),
                "preflight_worker_scenario_id_v1": str(row.get("scenario_id") or ""),
            }
        raw_out = row.get("replay_outcomes_json")
        if not isinstance(raw_out, list) or not raw_out:
            return {
                "schema": "rm_preflight_wiring_audit_v1",
                "ok_v1": False,
                "skipped_v1": False,
                "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                "missing_stages_v1": ["no_replay_outcomes_for_preflight_v1"],
                "human_message_v1": "RM preflight: bounded replay returned no closed trades.",
                "memory_sink_event_count_v1": len(sink),
            }
        first = raw_out[0]
        if not isinstance(first, dict):
            return {
                "schema": "rm_preflight_wiring_audit_v1",
                "ok_v1": False,
                "skipped_v1": False,
                "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                "missing_stages_v1": ["invalid_first_outcome_v1"],
                "human_message_v1": "RM preflight: first outcome is not a dict.",
                "memory_sink_event_count_v1": len(sink),
            }
        trade_id = str(first.get("trade_id") or "").strip()
        scenario_id = str(row.get("scenario_id") or "").strip()
        n_sink_before_seam = len(sink)
        with rm_preflight_seam_early_exit_session_v1():
            seam = student_loop_seam_after_parallel_batch_v1(
                results=[row],
                run_id=str(job_id).strip(),
                exam_run_contract_request_v1=exam_run_contract_request_v1,
                operator_batch_audit=operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
            )
        if seam.get("skipped"):
            return {
                "schema": "rm_preflight_wiring_audit_v1",
                "ok_v1": False,
                "skipped_v1": False,
                "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                "missing_stages_v1": ["student_seam_skipped_v1"],
                "human_message_v1": str(seam.get("reason") or "seam skipped"),
                "memory_sink_event_count_v1": len(sink),
                "preflight_seam_audit_v1": seam,
            }
        if not seam.get("rm_preflight_wiring_early_exit_v1"):
            return {
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
            }
        seam_errs = [str(x) for x in (seam.get("errors") or []) if x]
        if seam_errs:
            return {
                "schema": "rm_preflight_wiring_audit_v1",
                "ok_v1": False,
                "skipped_v1": False,
                "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                "missing_stages_v1": ["student_seam_errors_v1"],
                "human_message_v1": "RM preflight: " + "; ".join(seam_errs[:12]),
                "memory_sink_event_count_v1": len(sink),
                "preflight_seam_audit_v1": seam,
            }
        ok_ev, missing = validate_rm_preflight_memory_sink_v1(sink, scenario_id=scenario_id, trade_id=trade_id)
        if not ok_ev:
            return {
                "schema": "rm_preflight_wiring_audit_v1",
                "ok_v1": False,
                "skipped_v1": False,
                "status_v1": FAILED_PREFLIGHT_STATUS_V1,
                "missing_stages_v1": missing,
                "human_message_v1": "RM preflight: incomplete reasoning trace — missing: " + ", ".join(missing),
                "memory_sink_event_count_v1": len(sink),
                "preflight_seam_audit_v1": seam,
                "preflight_trace_events_sample_v1": sink[n_sink_before_seam:][:40],
            }
        return {
            "schema": "rm_preflight_wiring_audit_v1",
            "ok_v1": True,
            "skipped_v1": False,
            "status_v1": "passed_rm_preflight_wiring_v1",
            "missing_stages_v1": [],
            "memory_sink_event_count_v1": len(sink),
            "preflight_seam_audit_v1": seam,
            "preflight_trade_id_v1": trade_id,
            "preflight_scenario_id_v1": scenario_id,
        }


__all__ = [
    "FAILED_PREFLIGHT_STATUS_V1",
    "REQUIRED_RM_PREFLIGHT_STAGES_V1",
    "rm_preflight_enabled_v1",
    "run_rm_preflight_wiring_v1",
    "should_skip_rm_preflight_v1",
    "validate_rm_preflight_memory_sink_v1",
]
