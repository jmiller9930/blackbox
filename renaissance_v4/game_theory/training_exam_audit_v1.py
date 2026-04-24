"""
Training exam audit (operator) — **non-guesswork** checklist for “did anything Student-shaped happen?”

This is **not** the same question as “did Run TW % beat Sys BL %?”. Referee economics can tie while
Student seam still ran (or conversely, seam can soft-fail while Referee completes).

Persisted on each scorecard line as ``training_exam_audit_v1`` (see ``record_parallel_batch_finished``).
"""

from __future__ import annotations

from typing import Any

SCHEMA = "training_exam_audit_v1"


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def build_training_exam_audit_v1(scorecard_line: dict[str, Any]) -> dict[str, Any]:
    """
    Build a deterministic audit from **one** batch scorecard JSON object (already denormalized).

    Returns a dict with:
    - ``training_learning_verdict_v1`` — coarse outcome for operators / AI triage
    - ``checks_v1`` — pass/fail + source field path for each claim
    - ``troubleshooting_steps_v1`` — ordered human/AI steps when evidence is weak
    """
    job_id = str(scorecard_line.get("job_id") or "").strip()
    status = str(scorecard_line.get("status") or "").strip().lower()

    rows_appended = _int(scorecard_line.get("student_learning_rows_appended"), 0)
    retr = _int(scorecard_line.get("student_retrieval_matches"), 0)
    llm_rej = _int(scorecard_line.get("llm_student_output_rejections_v1"), 0)
    shadow = bool(scorecard_line.get("shadow_student_enabled"))

    mci = scorecard_line.get("memory_context_impact_audit_v1")
    mem_impact_yes = isinstance(mci, dict) and str(mci.get("memory_impact_yes_no") or "").upper() == "YES"
    recall_sum = _int(mci.get("recall_match_windows_total_sum"), 0) if isinstance(mci, dict) else 0
    bias_sum = _int(mci.get("recall_bias_applied_total_sum"), 0) if isinstance(mci, dict) else 0
    sig_bias_sum = _int(mci.get("recall_signal_bias_applied_total_sum"), 0) if isinstance(mci, dict) else 0

    llm_ex = scorecard_line.get("student_llm_execution_v1")
    ollama_ok = _int(llm_ex.get("ollama_trades_succeeded"), 0) if isinstance(llm_ex, dict) else 0
    ollama_att = _int(llm_ex.get("ollama_trades_attempted"), 0) if isinstance(llm_ex, dict) else 0

    oba = scorecard_line.get("operator_batch_audit")
    cmem = str(oba.get("context_signature_memory_mode") or "").strip().lower() if isinstance(oba, dict) else ""

    persisted_store = rows_appended > 0
    retrieval_engaged = retr > 0
    harness_counters = recall_sum > 0 or bias_sum > 0 or sig_bias_sum > 0
    harness_lane = mem_impact_yes or harness_counters
    llm_produced = ollama_ok > 0

    checks: list[dict[str, Any]] = [
        {
            "id": "persisted_student_learning_rows",
            "pass": persisted_store,
            "detail": rows_appended,
            "source": "scorecard_line.student_learning_rows_appended",
        },
        {
            "id": "student_retrieval_matches",
            "pass": retrieval_engaged,
            "detail": retr,
            "source": "scorecard_line.student_retrieval_matches",
        },
        {
            "id": "memory_context_impact_yes",
            "pass": mem_impact_yes,
            "detail": mci.get("memory_impact_yes_no") if isinstance(mci, dict) else None,
            "source": "scorecard_line.memory_context_impact_audit_v1.memory_impact_yes_no",
        },
        {
            "id": "recall_or_bias_counters",
            "pass": harness_counters,
            "detail": {"recall_match_windows_total_sum": recall_sum, "bias": bias_sum, "sig_bias": sig_bias_sum},
            "source": "scorecard_line.memory_context_impact_audit_v1",
        },
        {
            "id": "llm_trades_succeeded",
            "pass": llm_produced,
            "detail": {"succeeded": ollama_ok, "attempted": ollama_att, "rejections": llm_rej},
            "source": "scorecard_line.student_llm_execution_v1",
        },
        {
            "id": "shadow_student_lane_enabled",
            "pass": shadow,
            "detail": shadow,
            "source": "scorecard_line.shadow_student_enabled",
        },
    ]

    if status in ("error", "cancelled"):
        verdict = "INSUFFICIENT_BATCH_STATUS"
        reason = f"batch_status={status!r} — Student seam audit is not a completion proof here."
    elif status != "done":
        verdict = "INSUFFICIENT_BATCH_STATUS"
        reason = f"batch_status={status!r}"
    elif persisted_store:
        verdict = "PERSISTED_LEARNING_ROWS"
        reason = "At least one student_learning_record_v1 row was appended to the Student store for this job_id."
    elif retrieval_engaged or llm_produced:
        verdict = "ENGAGEMENT_WITHOUT_STORE_WRITES"
        reason = (
            "Retrieval and/or LLM path fired, but zero learning rows were appended — inspect "
            "student_loop_seam_audit_v1.errors and governance rejects on the parallel result payload."
        )
    elif harness_lane and cmem in ("read", "read_write"):
        verdict = "HARNESS_MEMORY_COUNTERS_ONLY"
        reason = (
            "Harness memory/recall counters suggest engagement, but no store writes and no retrieval/LLM success "
            "flags on this scorecard line — Referee path may dominate; verify learning_run_audit_v1 per scenario."
        )
    elif cmem in ("read", "read_write"):
        verdict = "NO_SCORECARD_EVIDENCE_OF_STUDENT_PATH"
        reason = (
            "Context memory mode was read/read_write but this line shows no appended rows, no retrieval matches, "
            "and no successful LLM trades — treat as 'Student lane did not demonstrate persistence on this run'."
        )
    else:
        verdict = "STUDENT_LANE_NOT_CONFIGURED_OR_OFF"
        cmem_disp = repr(cmem) if cmem else "off"
        reason = f"context_signature_memory_mode={cmem_disp} — Student seam may be inactive by configuration."

    steps = [
        "Open the parallel batch JSON for this job_id and read student_loop_directive_09_v1 (seam audit).",
        "If verdict is ENGAGEMENT_WITHOUT_STORE_WRITES: read errors[], soft_fail, memory_promotion_batch_v1, learning_loop_governance_v1.",
        "Compare learning_batch_audit_v1.replay_* sums vs expectation for recipe (harness vs baseline-only).",
        "If Referee trade win % ties baseline but verdict is not PERSISTED_LEARNING_ROWS: do not infer 'no learning' from TW alone.",
        "For exam-pack process (P): use exam fields + l1_p_value_source_v1; data_gap means process compare is blocked.",
    ]

    return {
        "schema": SCHEMA,
        "job_id": job_id or None,
        "batch_status_echo": status or None,
        "context_signature_memory_mode_echo": cmem or None,
        "training_learning_verdict_v1": verdict,
        "training_learning_verdict_reason_v1": reason,
        "checks_v1": checks,
        "troubleshooting_steps_v1": steps,
        "definitions_v1": {
            "persisted_learning": "student_learning_rows_appended > 0 (append_student_learning_record_v1 succeeded).",
            "engagement": "retrieval_matches > 0 and/or LLM succeeded trades and/or harness counters > 0.",
            "not_referee_tie_breaker": "Run TW % vs Sys BL % is a separate Referee rollup; see L1 dictionary.",
        },
    }
