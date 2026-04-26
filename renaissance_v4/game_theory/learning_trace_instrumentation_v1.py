"""
learning_trace_instrumentation_v1 — **parent-process** emits to ``learning_trace_events_v1``.

Workers in ``ProcessPoolExecutor`` must **not** append JSONL directly (interleaved writes). All
events here run from the Flask batch thread, ``student_loop_seam_after_parallel_batch_v1``, or
``record_parallel_batch_finished`` (single-threaded per job completion path).
"""

from __future__ import annotations

import os
import sys
from typing import Any

from renaissance_v4.game_theory.learning_trace_events_v1 import append_learning_trace_event_from_kwargs_v1
from renaissance_v4.game_theory.student_panel_l1_road_v1 import scorecard_line_fingerprint_sha256_40_v1


def learning_trace_instrumentation_enabled_v1() -> bool:
    """Disable all emits with ``PATTERN_GAME_LEARNING_TRACE_EVENTS=0`` (tests / emergency)."""
    v = os.environ.get("PATTERN_GAME_LEARNING_TRACE_EVENTS", "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def fingerprint_for_parallel_job_v1(
    *,
    operator_batch_audit: dict[str, Any] | None,
    fingerprint_preview: str | None,
    scorecard_line: dict[str, Any] | None = None,
) -> str | None:
    if fingerprint_preview and str(fingerprint_preview).strip():
        return str(fingerprint_preview).strip()[:64]
    if isinstance(scorecard_line, dict):
        fp = scorecard_line_fingerprint_sha256_40_v1(scorecard_line)
        if fp:
            return fp
    if isinstance(operator_batch_audit, dict) and operator_batch_audit:
        return scorecard_line_fingerprint_sha256_40_v1({"operator_batch_audit": operator_batch_audit})
    return None


def _emit(**kwargs: Any) -> None:
    if not learning_trace_instrumentation_enabled_v1():
        return
    try:
        append_learning_trace_event_from_kwargs_v1(**kwargs)
    except Exception as e:
        print(f"[learning_trace_instrumentation_v1] emit failed: {e}", file=sys.stderr)


def emit_referee_execution_started_v1(*, job_id: str, fingerprint: str | None, scenario_total: int) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="referee_execution_started",
        status="running",
        summary=f"Parallel worker batch scheduled ({scenario_total} scenario(s)).",
        producer="pattern_game_parallel_v1",
        evidence_payload={"scenario_total": scenario_total},
    )


def emit_referee_execution_completed_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    results: list[dict[str, Any]] | None,
) -> None:
    rows = list(results or [])
    n = len(rows)
    ok_n = sum(1 for r in rows if r.get("ok"))
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="referee_execution_completed",
        status="pass" if ok_n == n and n > 0 else "partial",
        summary=f"Worker replay rows returned: ok={ok_n}/{n}.",
        producer="pattern_game_parallel_v1",
        evidence_payload={"ok_count": ok_n, "total": n},
    )


def emit_packet_built_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    batch_dir: str | None,
    scenario_count: int,
) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="packet_built",
        status="pass" if batch_dir else "partial",
        summary="batch_parallel_results_v1 written under session batch dir."
        if batch_dir
        else "session batch dir missing — packet artifact path unknown.",
        producer="pattern_game_session_log_v1",
        evidence_payload={"session_log_batch_dir": batch_dir, "scenario_count": scenario_count},
    )


def emit_grading_completed_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    exam_e: Any,
    exam_p: Any,
    exam_pass: Any,
) -> None:
    has = exam_e is not None or exam_p is not None or exam_pass is not None
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="grading_completed",
        status="pass" if has else "partial",
        summary="Exam E/P denorm merged into scorecard record." if has else "No exam E/P on scorecard line after merge.",
        producer="batch_scorecard_v1",
        evidence_payload={
            "exam_e_score_v1": exam_e,
            "exam_p_score_v1": exam_p,
            "exam_pass_v1": exam_pass,
        },
    )


def emit_seam_disabled_placeholder_events_v1(*, job_id: str, fingerprint: str | None, reason: str) -> None:
    """When Directive 09 seam is off, still satisfy integrity with explicit skipped captures."""
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="memory_retrieval_completed",
        status="skipped",
        summary=f"Student seam skipped — {reason[:300]}",
        producer="student_loop_seam_v1",
        evidence_payload={"seam_skipped": True},
    )
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="student_output_sealed",
        status="skipped",
        summary="Student seam skipped — no Student output sealed in this process.",
        producer="student_loop_seam_v1",
        evidence_payload={"seam_skipped": True},
    )
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="referee_used_student_output",
        status="unknown",
        summary="Student seam did not run — cannot relate Student output to Referee replay in-process.",
        producer="student_loop_seam_v1",
        evidence_payload={"seam_skipped": True},
    )


def emit_memory_retrieval_completed_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str,
    trade_id: str,
    retrieval_matches: int,
    candle_timeframe_minutes: int | None = None,
    retrieval_signature_key: str | None = None,
) -> None:
    st = "pass" if retrieval_matches > 0 else "partial"
    ev: dict[str, Any] = {"student_retrieval_matches": retrieval_matches}
    if candle_timeframe_minutes is not None:
        ev["candle_timeframe_minutes"] = int(candle_timeframe_minutes)
    if retrieval_signature_key is not None and str(retrieval_signature_key).strip():
        ev["retrieval_signature_key"] = str(retrieval_signature_key).strip()[:2000]
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="memory_retrieval_completed",
        status=st,
        summary=f"Packet retrieval slices matched: {retrieval_matches}.",
        producer="student_loop_seam_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload=ev,
    )


def emit_llm_called_v1(
    *, job_id: str, fingerprint: str | None, scenario_id: str, trade_id: str, model: str | None
) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="llm_called",
        status="running",
        summary="Ollama Student thesis call started.",
        producer="student_ollama_student_output_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload={"llm_model": model},
    )


def emit_llm_output_received_v1(
    *, job_id: str, fingerprint: str | None, scenario_id: str, trade_id: str
) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="llm_output_received",
        status="pass",
        summary="Student LLM output sealed for trade.",
        producer="student_ollama_student_output_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload={},
    )


def emit_llm_output_rejected_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str,
    trade_id: str,
    errors: list[str],
) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="llm_output_rejected",
        status="fail",
        summary="; ".join(errors)[:2000],
        producer="student_ollama_student_output_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload={"errors": errors[:20]},
    )


def emit_student_output_sealed_v1(
    *, job_id: str, fingerprint: str | None, scenario_id: str, trade_id: str, via: str
) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="student_output_sealed",
        status="pass",
        summary=f"Student output ready for reveal ({via}).",
        producer="student_loop_seam_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload={"via": via},
    )


def emit_governance_decided_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str,
    trade_id: str,
    decision: str,
    reason_codes: list[Any],
) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="governance_decided",
        status=str(decision or "unknown").strip().lower()[:32],
        summary=f"GT018 governance decision={decision!r}.",
        producer="learning_memory_promotion_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload={"decision": decision, "reason_codes": reason_codes},
    )


def emit_learning_record_appended_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str,
    trade_id: str,
    record_id: str,
    candle_timeframe_minutes: int | None = None,
) -> None:
    ev: dict[str, Any] = {"record_id": record_id}
    if candle_timeframe_minutes is not None:
        ev["candle_timeframe_minutes"] = int(candle_timeframe_minutes)
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="learning_record_appended",
        status="pass",
        summary="student_learning_record_v1 appended to store.",
        producer="student_proctor_store_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload=ev,
    )


def emit_candle_timeframe_nexus_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    nexus: str,
    candle_timeframe_minutes: int,
    scenario_id: str | None = None,
    trade_id: str | None = None,
) -> None:
    """GT_DIRECTIVE_026TF — one of run_contract / replay / student_packet scope strings."""
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="candle_timeframe_nexus_v1",
        status="pass",
        summary=f"Timeframe handoff: {nexus}={candle_timeframe_minutes}m.",
        producer="candle_timeframe_trace_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload={
            "candle_timeframe_nexus": str(nexus or "").strip()[:128],
            "candle_timeframe_minutes": int(candle_timeframe_minutes),
        },
    )


def emit_timeframe_mismatch_detected_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    left_role: str,
    left_minutes: int,
    right_role: str,
    right_minutes: int,
    scenario_id: str | None = None,
) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="timeframe_mismatch_detected_v1",
        status="fail",
        summary=f"Timeframe mismatch: {left_role}={left_minutes}m vs {right_role}={right_minutes}m.",
        producer="candle_timeframe_trace_v1",
        scenario_id=scenario_id,
        evidence_payload={
            "left_role": str(left_role)[:120],
            "left_minutes": int(left_minutes),
            "right_role": str(right_role)[:120],
            "right_minutes": int(right_minutes),
        },
    )


def emit_referee_used_student_output_batch_truth_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    student_influence_on_worker_replay_v1: str,
    detail: str,
) -> None:
    """
    ``student_influence_on_worker_replay_v1``: ``true`` | ``false`` | ``unknown`` per product contract.

    Current architecture: Referee replay completes in parallel workers **before** the Student seam
    mutates learning rows — Student thesis does **not** change those worker outcomes, so default emit
    is ``false`` unless a future joint replay proves otherwise.
    """
    st = str(student_influence_on_worker_replay_v1 or "unknown").strip().lower()
    if st not in ("true", "false", "unknown"):
        st = "unknown"
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="referee_used_student_output",
        status=st,
        summary=detail[:2000],
        producer="student_loop_seam_v1",
        evidence_payload={"student_influence_on_worker_replay_v1": st},
    )


def emit_reasoning_router_decision_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    decision: dict[str, Any] | None = None,
    call_record: dict[str, Any] | None = None,
) -> None:
    """GT_DIRECTIVE_026AI — single router decision (no API keys, no raw provider blobs)."""
    d = {k: v for k, v in (decision or {}).items() if "key" not in k.lower()}
    cr = None
    if isinstance(call_record, dict):
        cr = {k: v for k, v in call_record.items() if "key" not in k.lower() and "api_key" not in k.lower()}
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="reasoning_router_decision_v1",
        status="pass" if d else "partial",
        summary="Unified reasoning router decision (local primary; external optional).",
        producer="unified_agent_v1",
        evidence_payload={"reasoning_router_decision_v1": d, "call_ledger_sanitized_v1": cr or {}},
    )


def emit_reasoning_cost_governor_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    snapshot: dict[str, Any] | None = None,
    call_record: dict[str, Any] | None = None,
) -> None:
    """GT_DIRECTIVE_026AI — token/call budget state (no secrets)."""
    cr = None
    if isinstance(call_record, dict):
        cr = {k: v for k, v in call_record.items() if "key" not in k.lower()}
    pl = {
        "reasoning_cost_governor_v1": snapshot or {},
        "call_ledger_sanitized_v1": cr or {},
    }
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="reasoning_cost_governor_v1",
        status="pass",
        summary="Reasoning cost governor snapshot.",
        producer="unified_agent_v1",
        evidence_payload=pl,
    )


def emit_external_reasoning_review_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    review: dict[str, Any] | None = None,
) -> None:
    """GT_DIRECTIVE_026AI — external advisory only (not execution authority)."""
    rv = {k: v for k, v in (review or {}).items() if "key" not in k.lower()}
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="external_reasoning_review_v1",
        status="pass" if rv else "partial",
        summary="External OpenAI reasoning review (advisory).",
        producer="unified_agent_v1",
        evidence_payload={"external_reasoning_review_v1": rv},
    )


def emit_student_reasoning_fault_map_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str | None = None,
    trade_id: str | None = None,
    student_reasoning_fault_map_v1: dict[str, Any] | None = None,
) -> None:
    """GT_DIRECTIVE_026R — one snapshot of the full node list for this trade (visibility)."""
    pl = student_reasoning_fault_map_v1 if isinstance(student_reasoning_fault_map_v1, dict) else {}
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="student_reasoning_fault_map_v1",
        status="pass" if pl else "partial",
        summary="Student reasoning fault map (node-level visibility).",
        producer="student_reasoning_fault_map_v1",
        trade_id=trade_id,
        scenario_id=scenario_id,
        evidence_payload={"student_reasoning_fault_map_v1": pl},
    )


def emit_lifecycle_reasoning_stage_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    lifecycle_reasoning_stage_v1: dict[str, Any] | None = None,
    trade_id: str | None = None,
    scenario_id: str | None = None,
) -> None:
    """GT_DIRECTIVE_026B — one bar of in-trade lifecycle (deterministic; observable in learning_trace JSONL)."""
    st = lifecycle_reasoning_stage_v1 if isinstance(lifecycle_reasoning_stage_v1, dict) else {}
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="lifecycle_reasoning_stage_v1",
        status="pass" if st else "partial",
        summary="lifecycle_reasoning_engine_v1: one bar (phase, decision, thesis/risk).",
        producer="lifecycle_reasoning_engine_v1",
        trade_id=trade_id,
        scenario_id=scenario_id,
        evidence_payload={"lifecycle_reasoning_stage_v1": st},
    )


def emit_lifecycle_tape_summary_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    lifecycle_tape_result_v1: dict[str, Any] | None = None,
    trade_id: str | None = None,
    scenario_id: str | None = None,
) -> None:
    """026B — end-of-tape roll-up (per_bar rows bounded in payload)."""
    tr = lifecycle_tape_result_v1 if isinstance(lifecycle_tape_result_v1, dict) else {}
    per = tr.get("per_bar_v1") or []
    slim = []
    for row in per[:256]:
        if not isinstance(row, dict):
            continue
        le = row.get("lifecycle_reasoning_eval_v1")
        stg = row.get("lifecycle_reasoning_stage_v1")
        slim.append(
            {
                "bar_index": row.get("bar_index"),
                "decision_v1": (le or {}).get("decision_v1"),
                "phase_v1": (le or {}).get("phase_v1"),
                "exit_reason_code_v1": (le or {}).get("exit_reason_code_v1"),
                "lifecycle_reasoning_stage_v1": stg if isinstance(stg, dict) else None,
            }
        )
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="lifecycle_tape_summary_v1",
        status="pass" if tr else "partial",
        summary="Lifecycle tape completed (or partial); see per_bar_slim_v1 in evidence.",
        producer="lifecycle_reasoning_engine_v1",
        trade_id=trade_id,
        scenario_id=scenario_id,
        evidence_payload={
            "lifecycle_tape_result_v1": {
                "schema": tr.get("schema"),
                "closed_v1": tr.get("closed_v1"),
                "exit_at_bar_index_v1": tr.get("exit_at_bar_index_v1"),
                "exit_reason_code_v1": tr.get("exit_reason_code_v1"),
                "per_bar_slim_v1": slim,
            }
        },
    )


def emit_entry_reasoning_pipeline_stage_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    stage: str,
    inputs: Any,
    outputs: Any,
    evidence: dict[str, Any] | None = None,
) -> None:
    """
    GT_DIRECTIVE_026A_IMPL — one stage of the entry reasoning engine (in-process trace).

    ``outputs`` / ``inputs`` may be large; keep evidence bounded in production if needed.
    """
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage=stage,
        status="pass",
        summary=f"entry_reasoning_engine_v1: {stage}",
        producer="entry_reasoning_engine_v1",
        evidence_payload={
            "entry_reasoning_stage": stage,
            "inputs": inputs,
            "outputs": outputs,
            "evidence": evidence or {},
        },
    )


__all__ = [
    "emit_candle_timeframe_nexus_v1",
    "emit_entry_reasoning_pipeline_stage_v1",
    "emit_lifecycle_reasoning_stage_v1",
    "emit_lifecycle_tape_summary_v1",
    "emit_reasoning_cost_governor_v1",
    "emit_reasoning_router_decision_v1",
    "emit_external_reasoning_review_v1",
    "emit_student_reasoning_fault_map_v1",
    "emit_governance_decided_v1",
    "emit_grading_completed_v1",
    "emit_learning_record_appended_v1",
    "emit_llm_called_v1",
    "emit_llm_output_received_v1",
    "emit_llm_output_rejected_v1",
    "emit_memory_retrieval_completed_v1",
    "emit_packet_built_v1",
    "emit_referee_execution_completed_v1",
    "emit_referee_execution_started_v1",
    "emit_referee_used_student_output_batch_truth_v1",
    "emit_seam_disabled_placeholder_events_v1",
    "emit_student_output_sealed_v1",
    "emit_timeframe_mismatch_detected_v1",
    "fingerprint_for_parallel_job_v1",
    "learning_trace_instrumentation_enabled_v1",
]
