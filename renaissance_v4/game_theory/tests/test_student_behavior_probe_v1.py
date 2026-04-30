"""Student behavior probe — gates + helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory.student_behavior_probe_v1 import (
    evaluate_student_behavior_probe_gates_v1,
    evaluate_full_student_run_contract_v1,
    execute_student_behavior_probe_v1,
    skip_student_behavior_probe_requested_v1,
)
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    _apply_canonical_student_action_v1,
)


def test_skip_student_behavior_probe_requested_v1() -> None:
    assert skip_student_behavior_probe_requested_v1(None) is False
    assert skip_student_behavior_probe_requested_v1({}) is False
    assert skip_student_behavior_probe_requested_v1({"skip_student_probe_v1": True}) is True
    assert skip_student_behavior_probe_requested_v1({"skip_student_probe_v1": "yes"}) is True
    assert skip_student_behavior_probe_requested_v1({"skip_student_behavior_probe_v1": 1}) is True


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


def test_probe_gates_pass_single_sealed_v1() -> None:
    """At least one authority-aligned seal satisfies the probe gate (latency-friendly bar)."""
    ok, errs = evaluate_student_behavior_probe_gates_v1(
        metrics={
            "authority_count_v1": 1,
            "sealed_count_v1": 1,
            "rejection_count_v1": 0,
            "contract_violation_count_v1": 0,
        },
        wall_clock_s_v1=30.0,
        wall_limit_s_v1=120.0,
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
            "authority_count_v1": 0,
            "sealed_count_v1": 0,
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


def test_full_run_contract_ok_when_bounded_seam_stop_reason_v1() -> None:
    """GT067 — capped seam trades use completed_bounded_seam_trades_v1; must not fail contract on stop reason alone."""
    r = evaluate_full_student_run_contract_v1(
        "nonexistent_job_bounded_seam_contract_test_v1",
        {"student_seam_stop_reason_v1": "completed_bounded_seam_trades_v1"},
    )
    reasons = list(r.get("contract_failure_reasons_v1") or [])
    assert all(not str(x).startswith("student_seam_stop_reason_not_completed_v1") for x in reasons)


def test_execute_probe_operator_cancel_before_seam_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operator cancel must resolve without waiting for subprocess wall SLA."""
    monkeypatch.setenv("PATTERN_GAME_STUDENT_PROBE_SUBPROCESS_ISOLATION", "1")
    root = Path(__file__).resolve().parents[2]
    manifest = root / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not manifest.is_file():
        pytest.skip("baseline manifest missing")
    scenarios = [{"scenario_id": "probe_cancel_t", "manifest_path": str(manifest)}]
    fail, summ = execute_student_behavior_probe_v1(
        scenarios=scenarios,
        main_job_id="a" * 32,
        exam_run_contract_request_v1={"student_brain_profile_v1": "memory_context_llm_student"},
        operator_batch_audit={"operator_recipe_id": "custom"},
        telemetry_dir=None,
        strategy_id=None,
        probe_cancel_check_v1=lambda: True,
    )
    assert fail is None
    assert isinstance(summ, dict)
    assert summ.get("probe_cancelled_v1") is True
    assert summ.get("probe_outcome_v1") == "CANCELLED"
