"""
Student **behavior preflight** — bounded seam sample after RM preflight PASS, before full parallel.

Fails fast when LLM + seal pipeline cannot produce healthy sealed outputs (Operator Student LLM profile).
"""

from __future__ import annotations

import copy
import os
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    normalize_student_reasoning_mode_v1,
)
from renaissance_v4.game_theory.learning_trace_events_v1 import SCHEMA_EVENT, read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl


SCHEMA_FAILED_STUDENT_BEHAVIOR_PREFLIGHT_V1 = "failed_student_behavior_preflight_v1"


def student_behavior_preflight_enabled_v1() -> bool:
    v = (os.environ.get("PATTERN_GAME_STUDENT_BEHAVIOR_PREFLIGHT") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def student_behavior_preflight_max_closed_trades_v1() -> int:
    raw = (os.environ.get("PATTERN_GAME_STUDENT_BEHAVIOR_PREFLIGHT_MAX_TRADES") or "").strip()
    try:
        n = int(raw) if raw else 40
    except ValueError:
        n = 40
    return max(20, min(50, n))


def student_behavior_preflight_calendar_months_v1() -> int:
    raw = (os.environ.get("PATTERN_GAME_STUDENT_BEHAVIOR_PREFLIGHT_MONTHS") or "").strip()
    try:
        n = int(raw) if raw else 1
    except ValueError:
        n = 1
    return max(1, min(12, n))


def behavior_preflight_trace_job_id_v1(main_job_id: str) -> str:
    base = str(main_job_id or "").strip()
    suf = "_sb_pf"
    if len(base) + len(suf) > 64:
        return base[: 64 - len(suf)] + suf
    return base + suf


def scenarios_with_behavior_preflight_window_v1(
    scenarios: list[dict[str, Any]],
    *,
    calendar_months_cap: int,
) -> list[dict[str, Any]]:
    """Shallow-ish copy with ``evaluation_window.calendar_months`` capped for faster referee."""
    cap = max(1, min(12, int(calendar_months_cap)))
    out: list[dict[str, Any]] = []
    for s in scenarios:
        sc = copy.deepcopy(s)
        ew = sc.get("evaluation_window") if isinstance(sc.get("evaluation_window"), dict) else {}
        ew = dict(ew)
        try:
            prev_m = int(ew.get("calendar_months") or 12)
        except (TypeError, ValueError):
            prev_m = 12
        ew["calendar_months"] = min(prev_m, cap)
        ew["behavior_preflight_window_clamp_v1"] = True
        sc["evaluation_window"] = ew
        out.append(sc)
    return out


def truncate_parallel_results_to_max_closed_trades_v1(
    results: list[dict[str, Any]],
    max_trades: int,
) -> list[dict[str, Any]]:
    """Keep successful rows but slice ``replay_outcomes_json`` until ``max_trades`` outcomes total."""
    remaining = max(0, int(max_trades))
    out: list[dict[str, Any]] = []
    for row in results or []:
        if not row.get("ok"):
            out.append(copy.deepcopy(row))
            continue
        rj = row.get("replay_outcomes_json")
        if not isinstance(rj, list) or remaining <= 0:
            nr = copy.deepcopy(row)
            nr["replay_outcomes_json"] = []
            out.append(nr)
            continue
        take = rj[:remaining]
        remaining -= len(take)
        nr = copy.deepcopy(row)
        nr["replay_outcomes_json"] = take
        out.append(nr)
    return out


def _metrics_from_trace_events_v1(events: list[dict[str, Any]]) -> dict[str, Any]:
    auth = sealed = rej = no_trade = 0
    failures: list[dict[str, Any]] = []
    for ev in events:
        if str(ev.get("schema") or "") != SCHEMA_EVENT:
            continue
        st = str(ev.get("stage") or "")
        if st == "student_decision_authority_v1":
            auth += 1
        elif st == "student_output_sealed":
            sealed += 1
            ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
            echo = str(ep.get("student_action_v1_echo") or "").strip().lower()
            if echo == "no_trade":
                no_trade += 1
        elif st == "llm_output_rejected":
            rej += 1
            if len(failures) < 12:
                ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
                errs = ep.get("errors") if isinstance(ep.get("errors"), list) else []
                failures.append(
                    {
                        "scenario_id": ev.get("scenario_id"),
                        "trade_id": ev.get("trade_id"),
                        "errors": [str(x) for x in errs[:12]],
                        "summary": str(ev.get("summary") or "")[:800],
                    }
                )
    return {
        "authority_count_v1": auth,
        "sealed_count_v1": sealed,
        "llm_output_rejected_count_v1": rej,
        "no_trade_count_v1": no_trade,
        "failure_samples_v1": failures[:3],
    }


def closed_trades_total_v1(results: list[dict[str, Any]]) -> int:
    n = 0
    for row in results or []:
        if not row.get("ok"):
            continue
        rj = row.get("replay_outcomes_json")
        if isinstance(rj, list):
            n += len(rj)
    return n


def evaluate_student_behavior_preflight_gates_v1(
    *,
    metrics: dict[str, Any],
) -> tuple[bool, list[str]]:
    errs: list[str] = []
    auth = int(metrics.get("authority_count_v1") or 0)
    sealed = int(metrics.get("sealed_count_v1") or 0)
    rej = int(metrics.get("llm_output_rejected_count_v1") or 0)

    if sealed <= 0:
        errs.append("gate_sealed_gt_zero_v1: sealed_count_v1 must be > 0")
    if auth != sealed:
        errs.append(f"gate_authority_equals_sealed_v1: authority_count_v1 ({auth}) != sealed_count_v1 ({sealed})")

    denom = rej + sealed
    if denom > 0 and rej > sealed * 2:
        errs.append(
            f"gate_rejection_not_dominant_v1: llm_output_rejected ({rej}) is dominant vs sealed ({sealed})"
        )

    return len(errs) == 0, errs


def build_failed_student_behavior_preflight_payload_v1(
    *,
    main_job_id: str,
    trace_job_id: str,
    closed_trades_sample_v1: int,
    metrics: dict[str, Any],
    gate_errors_v1: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_FAILED_STUDENT_BEHAVIOR_PREFLIGHT_V1,
        "ok_v1": False,
        "job_id": main_job_id,
        "behavior_preflight_trace_job_id_v1": trace_job_id,
        "closed_trades_sample_v1": closed_trades_sample_v1,
        "authority_count_v1": metrics.get("authority_count_v1"),
        "sealed_count_v1": metrics.get("sealed_count_v1"),
        "llm_output_rejected_count_v1": metrics.get("llm_output_rejected_count_v1"),
        "no_trade_count_v1": metrics.get("no_trade_count_v1"),
        "gate_errors_v1": gate_errors_v1,
        "first_three_failure_examples_v1": metrics.get("failure_samples_v1") or [],
    }


def evaluate_full_student_run_contract_v1(
    job_id: str,
    seam_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    WP3 — after full seam: fail contract if trace integrity or stop reason demands suppression.

    Sets ``operator_metrics_suppressed_v1`` when the Student seam did not complete successfully or
    trace authority/sealed counts are unhealthy.
    """
    from renaissance_v4.game_theory.learning_trace_events_v1 import count_learning_trace_terminal_integrity_v1

    jid = str(job_id or "").strip()
    reasons: list[str] = []
    intr = count_learning_trace_terminal_integrity_v1(jid)
    auth = int(intr.get("student_decision_authority_v1_count") or 0)
    sealed = int(intr.get("student_output_sealed_count") or 0)
    if auth <= 0:
        reasons.append("authority_count_zero_v1")
    if sealed <= 0:
        reasons.append("sealed_count_zero_v1")
    if not bool(intr.get("integrity_ok")):
        reasons.append("authority_ne_sealed_trace_integrity_v1")
    sr = str((seam_audit or {}).get("student_seam_stop_reason_v1") or "") if isinstance(seam_audit, dict) else ""
    if sr != "completed_all_trades_v1":
        reasons.append(f"student_seam_stop_reason_not_completed_v1:{sr or 'missing'}")
    failed = len(reasons) > 0
    return {
        "student_full_run_contract_failed_v1": failed,
        "operator_metrics_suppressed_v1": failed,
        "contract_failure_reasons_v1": reasons,
        "learning_trace_terminal_integrity_echo_v1": intr,
    }


def profile_requires_behavior_preflight_v1(exam_req: dict[str, Any] | None) -> bool:
    if not isinstance(exam_req, dict):
        return False
    prof = normalize_student_reasoning_mode_v1(
        str(exam_req.get("student_brain_profile_v1") or exam_req.get("student_reasoning_mode") or "")
    )
    return prof == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1


def execute_student_behavior_preflight_v1(
    *,
    scenarios: list[dict[str, Any]],
    main_job_id: str,
    exam_run_contract_request_v1: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    max_workers: int,
    experience_log_path: Any,
    progress_callback: Any,
    on_session_log_batch: Any,
    telemetry_dir: Any,
    telemetry_ctx: Any,
    cancel_check: Any,
    strategy_id: str | None,
) -> dict[str, Any] | None:
    """
    Run bounded referee + full Student seam on a clamped evaluation window; return failure payload or ``None``.

    Trace events use ``behavior_preflight_trace_job_id_v1(main_job_id)`` so full-run trace stays separate.
    """
    from pathlib import Path

    from renaissance_v4.game_theory.live_telemetry_v1 import clear_job_telemetry_files
    from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel
    from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
        student_loop_seam_after_parallel_batch_v1,
    )

    cap_m = student_behavior_preflight_calendar_months_v1()
    max_tr = student_behavior_preflight_max_closed_trades_v1()
    trace_jid = behavior_preflight_trace_job_id_v1(main_job_id)

    scenarios_pf = scenarios_with_behavior_preflight_window_v1(scenarios, calendar_months_cap=cap_m)
    workers = max(1, min(max_workers, len(scenarios_pf)))

    td = Path(str(telemetry_dir)) if telemetry_dir is not None else None
    if td is not None:
        clear_job_telemetry_files(trace_jid, base=td)

    results = run_scenarios_parallel(
        scenarios_pf,
        max_workers=workers,
        experience_log_path=experience_log_path,
        progress_callback=progress_callback,
        on_session_log_batch=on_session_log_batch,
        telemetry_job_id=trace_jid,
        telemetry_dir=td,
        telemetry_context=telemetry_ctx,
        cancel_check=cancel_check,
    )
    truncated = truncate_parallel_results_to_max_closed_trades_v1(results, max_tr)
    closed_n = closed_trades_total_v1(truncated)

    student_loop_seam_after_parallel_batch_v1(
        results=truncated,
        run_id=trace_jid,
        strategy_id=strategy_id,
        exam_run_contract_request_v1=exam_run_contract_request_v1
        if isinstance(exam_run_contract_request_v1, dict)
        else None,
        operator_batch_audit=operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
    )

    trace_path = default_learning_trace_events_jsonl()
    events = read_learning_trace_events_for_job_v1(trace_jid, path=trace_path, max_lines=2_000_000)
    metrics = _metrics_from_trace_events_v1(events)
    metrics["closed_trades_sample_v1"] = closed_n

    ok_gate, gate_errs = evaluate_student_behavior_preflight_gates_v1(metrics=metrics)
    if ok_gate:
        return None

    return build_failed_student_behavior_preflight_payload_v1(
        main_job_id=main_job_id,
        trace_job_id=trace_jid,
        closed_trades_sample_v1=closed_n,
        metrics=metrics,
        gate_errors_v1=gate_errs,
    )


__all__ = [
    "SCHEMA_FAILED_STUDENT_BEHAVIOR_PREFLIGHT_V1",
    "behavior_preflight_trace_job_id_v1",
    "build_failed_student_behavior_preflight_payload_v1",
    "closed_trades_total_v1",
    "evaluate_student_behavior_preflight_gates_v1",
    "profile_requires_behavior_preflight_v1",
    "scenarios_with_behavior_preflight_window_v1",
    "student_behavior_preflight_calendar_months_v1",
    "student_behavior_preflight_enabled_v1",
    "student_behavior_preflight_max_closed_trades_v1",
    "truncate_parallel_results_to_max_closed_trades_v1",
    "_metrics_from_trace_events_v1",
    "execute_student_behavior_preflight_v1",
    "evaluate_full_student_run_contract_v1",
]
