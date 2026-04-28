"""Student behavior probe — gates + helpers."""

from __future__ import annotations

from renaissance_v4.game_theory.student_behavior_probe_v1 import (
    evaluate_student_behavior_probe_gates_v1,
    evaluate_full_student_run_contract_v1,
)
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    _apply_canonical_student_action_v1,
)


def test_probe_gates_pass_v1() -> None:
    ok, errs = evaluate_student_behavior_probe_gates_v1(
        metrics={
            "authority_count_v1": 10,
            "sealed_count_v1": 10,
            "rejection_count_v1": 1,
            "contract_violation_count_v1": 0,
        },
        wall_clock_s_v1=2.0,
        wall_limit_s_v1=5.0,
    )
    assert ok is True
    assert errs == []


def test_probe_gates_fail_wall_clock_v1() -> None:
    ok, errs = evaluate_student_behavior_probe_gates_v1(
        metrics={
            "authority_count_v1": 10,
            "sealed_count_v1": 10,
            "rejection_count_v1": 0,
            "contract_violation_count_v1": 0,
        },
        wall_clock_s_v1=6.0,
        wall_limit_s_v1=5.0,
    )
    assert ok is False
    assert any("wall_clock" in e.lower() for e in errs)


def test_probe_gates_fail_sealed_min_v1() -> None:
    ok, errs = evaluate_student_behavior_probe_gates_v1(
        metrics={
            "authority_count_v1": 3,
            "sealed_count_v1": 3,
            "rejection_count_v1": 0,
            "contract_violation_count_v1": 0,
        },
        wall_clock_s_v1=1.0,
        wall_limit_s_v1=5.0,
    )
    assert ok is False
    assert any("sealed" in e.lower() for e in errs)


def test_probe_gates_fail_contract_violations_v1() -> None:
    ok, errs = evaluate_student_behavior_probe_gates_v1(
        metrics={
            "authority_count_v1": 10,
            "sealed_count_v1": 10,
            "rejection_count_v1": 0,
            "contract_violation_count_v1": 1,
        },
        wall_clock_s_v1=1.0,
        wall_limit_s_v1=5.0,
    )
    assert ok is False
    assert any("contract" in e.lower() for e in errs)


def test_probe_gates_fail_rejection_rate_v1() -> None:
    ok, errs = evaluate_student_behavior_probe_gates_v1(
        metrics={
            "authority_count_v1": 5,
            "sealed_count_v1": 5,
            "rejection_count_v1": 5,
            "contract_violation_count_v1": 0,
        },
        wall_clock_s_v1=1.0,
        wall_limit_s_v1=5.0,
    )
    assert ok is False
    assert any("rejection_rate" in e.lower() for e in errs)


def test_canonical_student_action_from_enter_long_v1() -> None:
    out: dict = {"student_action_v1": "enter_long", "act": False, "direction": "flat"}
    _apply_canonical_student_action_v1(out)
    assert out["act"] is True
    assert out["direction"] == "long"


def test_full_run_contract_fails_when_trace_counts_zero_v1() -> None:
    r = evaluate_full_student_run_contract_v1(
        "nonexistent_job_for_contract_test_v1",
        {"student_seam_stop_reason_v1": "completed_all_trades_v1"},
    )
    assert r.get("student_full_run_contract_failed_v1") is True


def test_full_run_contract_fails_when_stop_reason_not_completed_v1() -> None:
    r = evaluate_full_student_run_contract_v1(
        "nonexistent_job_for_contract_test_v2",
        {"student_seam_stop_reason_v1": "skipped_seam_disabled_v1"},
    )
    assert r.get("student_full_run_contract_failed_v1") is True
