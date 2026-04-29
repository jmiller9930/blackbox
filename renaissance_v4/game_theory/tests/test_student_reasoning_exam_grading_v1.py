"""Unit tests for GT038 grading helpers (no DB)."""

from __future__ import annotations

from renaissance_v4.game_theory.exam.student_reasoning_exam_grading_v1 import (
    detect_hallucination_v1,
    grade_scenario_v1,
)


def test_hallucination_detects_forbidden_markers() -> None:
    assert detect_hallucination_v1(raw_llm_text="guaranteed profit tomorrow", merge_errors=[]) is True
    assert detect_hallucination_v1(raw_llm_text="bounded risk only", merge_errors=[]) is False


def test_grade_strict_no_trade_chop() -> None:
    scen = {
        "scenario_id": "d6_s03_sideways_chop",
        "grade_primary_action_v1": "no_trade",
        "memory_injection_v1": None,
    }
    ere = {
        "decision_synthesis_v1": {"action": "no_trade"},
        "memory_context_eval_v1": {"aggregate_memory_effect_v1": "none"},
        "expected_value_risk_cost_v1": {"available_v1": False},
    }
    g = grade_scenario_v1(
        scenario=scen,
        ere=ere,
        final_so={"student_action_v1": "no_trade"},
        raw_llm_text="",
        merge_errors=[],
    )
    assert g["action_correct"] == "YES"
    assert g["no_trade_correct"] == "YES"


def test_grade_memory_conflict_fails_on_directional() -> None:
    scen = {
        "scenario_id": "d6_s10_memory_warning_trade",
        "grade_primary_action_v1": "memory_conflict",
        "memory_injection_v1": "negative",
    }
    ere = {
        "decision_synthesis_v1": {"action": "enter_long"},
        "memory_context_eval_v1": {"aggregate_memory_effect_v1": "conflict"},
        "expected_value_risk_cost_v1": {"available_v1": True, "preferred_action_v1": "no_trade"},
    }
    g = grade_scenario_v1(
        scenario=scen,
        ere=ere,
        final_so={"student_action_v1": "enter_long"},
        raw_llm_text="",
        merge_errors=[],
    )
    assert g["memory_alignment"] == "FAIL"
    assert g["ev_alignment"] == "FAIL"
