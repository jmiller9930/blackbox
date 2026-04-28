"""Unit tests for student_test_mode_v1 (trade budget + 026c isolation guard)."""

from __future__ import annotations

import os

import pytest

from renaissance_v4.game_theory.student_proctor.lifecycle_deterministic_learning_026c_v1 import (
    retrieve_applicable_learning_context_026c_v1,
)
from renaissance_v4.game_theory.student_test_mode_v1 import (
    STUDENT_TEST_INSUFFICIENT_TRADE_COUNT_V1,
    STUDENT_TEST_ISOLATION_ENV_V1,
    StudentTestInsufficientTradesError,
    apply_student_test_mode_env_v1,
    build_student_test_mode_parallel_results_from_db_anchors_v1,
    count_replay_outcomes_parallel_results_v1,
    student_test_mode_isolation_active_v1,
    truncate_parallel_results_to_trade_budget_v1,
)


def test_truncate_exact_ten_across_rows() -> None:
    results = [
        {"ok": True, "scenario_id": "a", "replay_outcomes_json": [{"t": i} for i in range(7)]},
        {"ok": True, "scenario_id": "b", "replay_outcomes_json": [{"t": i} for i in range(7)]},
    ]
    out = truncate_parallel_results_to_trade_budget_v1(results, budget=10)
    assert count_replay_outcomes_parallel_results_v1(out) == 10
    assert len(out[0]["replay_outcomes_json"]) == 7
    assert len(out[1]["replay_outcomes_json"]) == 3


def test_insufficient_raises() -> None:
    results = [{"ok": True, "replay_outcomes_json": [{"x": 1}]}]
    with pytest.raises(StudentTestInsufficientTradesError) as ei:
        truncate_parallel_results_to_trade_budget_v1(results)
    assert ei.value.total == 1
    assert STUDENT_TEST_INSUFFICIENT_TRADE_COUNT_V1 in str(ei.value)


def test_retrieve_026c_empty_when_isolation_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv(STUDENT_TEST_ISOLATION_ENV_V1, "1")
    monkeypatch.setenv("PATTERN_GAME_LIFECYCLE_DETERMINISTIC_LEARNING_026C_STORE", str(tmp_path / "x.jsonl"))
    assert student_test_mode_isolation_active_v1() is True
    assert (
        retrieve_applicable_learning_context_026c_v1(
            symbol="BTC",
            candle_timeframe_minutes=5,
            context_signature_key="k",
            decision_open_time_ms=9999999999999,
            store_path=tmp_path / "full.jsonl",
        )
        == []
    )


def test_build_student_test_from_db_anchors_empty_scenarios() -> None:
    rows, err = build_student_test_mode_parallel_results_from_db_anchors_v1(scenarios=[])
    assert rows is None
    assert err == "student_test_empty_scenarios_v1"


def test_apply_env_sets_expected_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BLACKBOX_PML_RUNTIME_ROOT", raising=False)
    env = apply_student_test_mode_env_v1("job-test-1")
    assert env["PATTERN_GAME_GROUNDHOG_BUNDLE"] == "0"
    assert env[STUDENT_TEST_ISOLATION_ENV_V1] == "1"
    assert "student_test" in env["BLACKBOX_PML_RUNTIME_ROOT"]
