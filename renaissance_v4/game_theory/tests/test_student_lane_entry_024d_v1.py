"""GT-024D — decision table for Student full-control vs baseline-gated replay entry."""

from __future__ import annotations

from types import SimpleNamespace

from renaissance_v4.research.replay_runner import _compute_student_lane_entry_v1


def _sig(active: bool, direction: str | None) -> SimpleNamespace:
    return SimpleNamespace(active=active, direction=direction)


def test_baseline_024c_no_intent_uses_fusion() -> None:
    open_, d, path = _compute_student_lane_entry_v1(
        flat=True,
        risk_decision_allowed=True,
        fusion_result_direction="long",
        has_directional_signal=True,
        signal_results=[_sig(True, "long")],
        student_execution_intent_v1=None,
        student_full_control_lane_v1=False,
    )
    assert open_ and d == "long" and path == "baseline_024c"


def test_baseline_024c_intent_no_trade_suppresses() -> None:
    open_, d, path = _compute_student_lane_entry_v1(
        flat=True,
        risk_decision_allowed=True,
        fusion_result_direction="long",
        has_directional_signal=True,
        signal_results=[_sig(True, "long")],
        student_execution_intent_v1={
            "schema": "student_execution_intent_v1",
            "action": "no_trade",
        },
        student_full_control_lane_v1=False,
    )
    assert not open_ and d is None and path is None


def test_full_control_024d_fusion_veto_opens() -> None:
    intent = {"schema": "student_execution_intent_v1", "action": "enter_long"}
    open_, d, path = _compute_student_lane_entry_v1(
        flat=True,
        risk_decision_allowed=True,
        fusion_result_direction="no_trade",
        has_directional_signal=True,
        signal_results=[_sig(True, "long"), _sig(True, "short")],
        student_execution_intent_v1=intent,
        student_full_control_lane_v1=True,
    )
    assert open_ and d == "long" and path == "full_control_024d_fusion_veto"


def test_full_control_requires_signal_alignment() -> None:
    intent = {"schema": "student_execution_intent_v1", "action": "enter_long"}
    open_, d, _path = _compute_student_lane_entry_v1(
        flat=True,
        risk_decision_allowed=True,
        fusion_result_direction="no_trade",
        has_directional_signal=True,
        signal_results=[_sig(True, "short")],
        student_execution_intent_v1=intent,
        student_full_control_lane_v1=True,
    )
    assert not open_ and d is None


def test_full_control_ignored_without_lane_flag() -> None:
    open_, d, _path = _compute_student_lane_entry_v1(
        flat=True,
        risk_decision_allowed=True,
        fusion_result_direction="no_trade",
        has_directional_signal=True,
        signal_results=[_sig(True, "long")],
        student_execution_intent_v1={"action": "enter_long"},
        student_full_control_lane_v1=False,
    )
    assert not open_
