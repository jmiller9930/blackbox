"""Directive — Student behavior preflight gates + canonical student_action_v1."""

from __future__ import annotations

from renaissance_v4.game_theory.student_behavior_preflight_v1 import (
    evaluate_student_behavior_preflight_gates_v1,
    evaluate_full_student_run_contract_v1,
)
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    _apply_canonical_student_action_v1,
)


def test_behavior_preflight_gates_pass_v1() -> None:
    ok, errs = evaluate_student_behavior_preflight_gates_v1(
        metrics={
            "authority_count_v1": 3,
            "sealed_count_v1": 3,
            "llm_output_rejected_count_v1": 1,
        }
    )
    assert ok is True
    assert errs == []


def test_behavior_preflight_gates_fail_sealed_zero_v1() -> None:
    ok, errs = evaluate_student_behavior_preflight_gates_v1(
        metrics={
            "authority_count_v1": 2,
            "sealed_count_v1": 0,
            "llm_output_rejected_count_v1": 1,
        }
    )
    assert ok is False
    assert any("sealed" in e.lower() for e in errs)


def test_behavior_preflight_gates_fail_auth_ne_sealed_v1() -> None:
    ok, errs = evaluate_student_behavior_preflight_gates_v1(
        metrics={
            "authority_count_v1": 2,
            "sealed_count_v1": 1,
            "llm_output_rejected_count_v1": 0,
        }
    )
    assert ok is False
    assert any("authority" in e.lower() for e in errs)


def test_behavior_preflight_gates_fail_rejection_dominant_v1() -> None:
    ok, errs = evaluate_student_behavior_preflight_gates_v1(
        metrics={
            "authority_count_v1": 5,
            "sealed_count_v1": 2,
            "llm_output_rejected_count_v1": 10,
        }
    )
    assert ok is False
    assert any("dominant" in e.lower() for e in errs)


def test_canonical_student_action_from_enter_long_v1() -> None:
    out: dict = {"student_action_v1": "enter_long", "act": False, "direction": "flat"}
    _apply_canonical_student_action_v1(out)
    assert out["act"] is True
    assert out["direction"] == "long"


def test_canonical_student_action_from_act_direction_when_sa_missing_v1() -> None:
    out: dict = {"act": True, "direction": "short"}
    _apply_canonical_student_action_v1(out)
    assert out["student_action_v1"] == "enter_short"


def test_canonical_student_action_no_trade_v1() -> None:
    out: dict = {"student_action_v1": "no_trade", "act": True, "direction": "long"}
    _apply_canonical_student_action_v1(out)
    assert out["act"] is False
    assert out["direction"] == "flat"


def test_full_run_contract_fails_when_trace_counts_zero_v1() -> None:
    """Empty/fresh trace: authority and sealed counts zero → contract failure."""
    r = evaluate_full_student_run_contract_v1(
        "nonexistent_job_for_contract_test_v1",
        {"student_seam_stop_reason_v1": "completed_all_trades_v1"},
    )
    assert r.get("student_full_run_contract_failed_v1") is True
    rs = r.get("contract_failure_reasons_v1") or []
    assert any("authority" in x or "sealed" in x for x in rs)


def test_full_run_contract_fails_when_stop_reason_not_completed_v1() -> None:
    r = evaluate_full_student_run_contract_v1(
        "nonexistent_job_for_contract_test_v2",
        {"student_seam_stop_reason_v1": "skipped_seam_disabled_v1"},
    )
    assert r.get("student_full_run_contract_failed_v1") is True
    rs = r.get("contract_failure_reasons_v1") or []
    assert any("stop_reason" in x for x in rs)
