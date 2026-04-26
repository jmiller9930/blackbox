"""Operator Run mode: Baseline vs Student (UI contract + control path)."""

from __future__ import annotations

from renaissance_v4.game_theory.exam_run_contract_v1 import STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.web_app import _prepare_parallel_payload

PAGE_MARKER = "id=\"examStudentReasoningModePick\""


def test_prepare_parallel_payload_baseline_forces_context_memory_off() -> None:
    body = {
        "operator_recipe_id": "pattern_learning",
        "evaluation_window_mode": "12",
        "trade_window_mode": "5m",
        "scenarios_json": "[]",
        "context_signature_memory_mode": "read_write",
        "exam_run_contract_v1": {
            "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
            "student_controlled_execution_v1": False,
        },
    }
    prep = _prepare_parallel_payload(body)
    assert prep["ok"] is True
    oba = prep["operator_batch_audit"]
    assert oba.get("context_signature_memory_mode") == "off"
    assert oba.get("operator_run_mode_surface_v1") == "baseline"
    for s in prep["scenarios"]:
        assert s.get("context_signature_memory_mode") == "off"


def test_embedded_page_has_only_baseline_and_student_options() -> None:
    from renaissance_v4.game_theory import web_app as wa

    html = wa.PAGE_HTML
    i = html.find(PAGE_MARKER)
    assert i != -1
    seg = html[i : i + 900]
    assert "value=\"baseline_no_memory_no_llm\">Baseline</option>" in seg
    assert "value=\"memory_context_llm_student\"" in seg and ">Student</option>" in seg
    assert "memory_context_student" not in seg or "pgExamLegacyBrainProfileOverride" in html


def test_baseline_brain_profile_skips_student_seam() -> None:
    audit = student_loop_seam_after_parallel_batch_v1(
        results=[{"ok": True, "scenario_id": "s1", "replay_outcomes_json": []}],
        run_id="run_baseline_x",
        exam_run_contract_request_v1={
            "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
            "student_controlled_execution_v1": False,
        },
    )
    assert audit.get("skipped") is True
    assert "baseline" in str(audit.get("reason") or "").lower() or audit.get("baseline_control_operator_mode_v1")
    assert int(audit.get("student_learning_rows_appended") or 0) == 0


def test_cumulative_026c_job_surface_baseline_is_not_applicable() -> None:
    from renaissance_v4.game_theory.learning_effect_closure_026c_v1 import cumulative_026c_job_surface_v1

    surf = cumulative_026c_job_surface_v1(
        {
            "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
            "operator_batch_audit": {"operator_run_mode_surface_v1": "baseline"},
        },
        [],
    )
    assert surf.get("outcome_v1") == "NOT_APPLICABLE"
