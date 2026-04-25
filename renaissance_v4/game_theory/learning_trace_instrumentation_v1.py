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
) -> None:
    st = "pass" if retrieval_matches > 0 else "partial"
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="memory_retrieval_completed",
        status=st,
        summary=f"Packet retrieval slices matched: {retrieval_matches}.",
        producer="student_loop_seam_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload={"student_retrieval_matches": retrieval_matches},
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
    *, job_id: str, fingerprint: str | None, scenario_id: str, trade_id: str, record_id: str
) -> None:
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="learning_record_appended",
        status="pass",
        summary="student_learning_record_v1 appended to store.",
        producer="student_proctor_store_v1",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload={"record_id": record_id},
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


__all__ = [
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
    "fingerprint_for_parallel_job_v1",
    "learning_trace_instrumentation_enabled_v1",
]
