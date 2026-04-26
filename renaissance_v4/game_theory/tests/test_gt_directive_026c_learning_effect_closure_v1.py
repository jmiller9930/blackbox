# GT_DIRECTIVE_026C addendum — learning_effect_closure_026c_v1

from __future__ import annotations

from unittest.mock import patch

from renaissance_v4.game_theory.learning_effect_closure_026c_v1 import (
    RESULT_INSUFFICIENT,
    RESULT_LEARNING_CHANGED_BEHAVIOR,
    RESULT_LEARNING_RETRIEVED_NO_CHANGE,
    RESULT_ROUTER_NOT_TRIGGERED,
    build_learning_effect_closure_026c_v1,
)


def _ev(stage: str, pl: dict) -> dict:
    return {
        "schema": "learning_trace_event_v1",
        "job_id": "job_b",
        "stage": stage,
        "evidence_payload": pl,
    }


def test_closure_router_not_triggered_when_no_router_event() -> None:
    with patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._events_for",
        return_value=[_ev("lifecycle_tape_summary_v1", {"lifecycle_tape_result_v1": {"retrieved_lifecycle_deterministic_learning_026c_v1": []}})],
    ), patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._governance_blocked",
        return_value=False,
    ), patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._scorecard_snapshot",
        return_value={"job_id": "c1", "student_action_v1": "enter_long"},
    ):
        o = build_learning_effect_closure_026c_v1(
            "job_b", run_a_job_id="job_a", control_job_id="c1", scorecard_entry_run_b={}
        )
    assert o.get("closure_result_v1") == RESULT_ROUTER_NOT_TRIGGERED


def test_closure_insufficient_without_control() -> None:
    with patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._events_for",
        return_value=[
            _ev(
                "reasoning_router_decision_v1",
                {
                    "reasoning_router_decision_v1": {"final_route_v1": "local_only", "escalation_blockers_v1": []},
                    "call_ledger_sanitized_v1": {},
                },
            ),
            _ev(
                "lifecycle_tape_summary_v1",
                {
                    "lifecycle_tape_result_v1": {
                        "retrieved_lifecycle_deterministic_learning_026c_v1": [
                            {"record_id_026c": "r1", "decay_weight_01": 0.9}
                        ],
                        "deterministic_learning_context_026c_v1": {"slice_count_v1": 1, "max_decay_weight_01": 0.9},
                    }
                },
            ),
        ],
    ), patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._governance_blocked",
        return_value=False,
    ), patch("renaissance_v4.game_theory.learning_effect_closure_026c_v1._lookup_026c_record_id", return_value=None):
        o = build_learning_effect_closure_026c_v1("job_b", run_a_job_id=None, control_job_id=None, scorecard_entry_run_b={})
    assert o.get("closure_result_v1") == RESULT_INSUFFICIENT


def test_closure_changed_when_deltas() -> None:
    with patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._events_for",
        return_value=[
            _ev(
                "reasoning_router_decision_v1",
                {
                    "reasoning_router_decision_v1": {"final_route_v1": "local_only", "escalation_blockers_v1": []},
                    "call_ledger_sanitized_v1": {},
                },
            ),
            _ev(
                "lifecycle_tape_summary_v1",
                {
                    "lifecycle_tape_result_v1": {
                        "retrieved_lifecycle_deterministic_learning_026c_v1": [{"record_id_026c": "r1"}],
                        "deterministic_learning_context_026c_v1": {"slice_count_v1": 1},
                    }
                },
            ),
        ],
    ), patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._governance_blocked",
        return_value=False,
    ), patch("renaissance_v4.game_theory.learning_effect_closure_026c_v1._lookup_026c_record_id", return_value=None):

        def _snap(jid: str):
            if jid == "job_b":
                return {"job_id": "job_b", "student_action_v1": "enter_long", "student_confidence_01": 0.9}
            if jid == "ctrl":
                return {"job_id": "ctrl", "student_action_v1": "no_trade", "student_confidence_01": 0.5}
            return None

        with patch(
            "renaissance_v4.game_theory.learning_effect_closure_026c_v1._scorecard_snapshot", side_effect=_snap
        ):
            o = build_learning_effect_closure_026c_v1(
                "job_b", run_a_job_id="job_a", control_job_id="ctrl", scorecard_entry_run_b={}
            )
    assert o.get("closure_result_v1") == RESULT_LEARNING_CHANGED_BEHAVIOR


def _same_stack_events() -> list:
    return [
        _ev(
            "reasoning_router_decision_v1",
            {
                "reasoning_router_decision_v1": {"final_route_v1": "local_only", "escalation_blockers_v1": []},
                "call_ledger_sanitized_v1": {},
            },
        ),
        _ev(
            "lifecycle_tape_summary_v1",
            {
                "lifecycle_tape_result_v1": {
                    "retrieved_lifecycle_deterministic_learning_026c_v1": [{"record_id_026c": "r1"}],
                    "deterministic_learning_context_026c_v1": {"slice_count_v1": 1},
                    "per_bar_slim_v1": [{"decision_v1": "hold"}, {"decision_v1": "exit"}],
                    "closed_v1": True,
                    "exit_reason_code_v1": "z",
                }
            },
        ),
    ]


def test_closure_no_change_when_equal() -> None:
    def _ev_for(jid: str) -> list:
        return _same_stack_events() if jid in ("job_b", "ctrl") else []

    with patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._events_for", side_effect=_ev_for
    ), patch("renaissance_v4.game_theory.learning_effect_closure_026c_v1._governance_blocked", return_value=False), patch(
        "renaissance_v4.game_theory.learning_effect_closure_026c_v1._lookup_026c_record_id", return_value=None
    ):

        def _snap2(j: str):
            return {
                "job_id": j,
                "student_action_v1": "enter_long",
                "student_confidence_01": 0.7,
                "exam_e_score_v1": 0.5,
            }

        with patch("renaissance_v4.game_theory.learning_effect_closure_026c_v1._scorecard_snapshot", side_effect=_snap2):
            o = build_learning_effect_closure_026c_v1(
                "job_b", run_a_job_id="a", control_job_id="ctrl", scorecard_entry_run_b={}
            )
    assert o.get("closure_result_v1") == RESULT_LEARNING_RETRIEVED_NO_CHANGE
