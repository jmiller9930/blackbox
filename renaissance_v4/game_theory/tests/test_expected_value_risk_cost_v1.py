"""GT_DIRECTIVE_032 — expected_value_risk_cost_v1 deterministic EV layer."""

from __future__ import annotations

from renaissance_v4.game_theory.reasoning_model.expected_value_risk_cost_v1 import (
    SCHEMA_EXPECTED_VALUE_RISK_COST_V1,
    compute_ev_score_adjustment_v1,
    compute_expected_value_risk_cost_v1,
)


def test_insufficient_sample_not_available() -> None:
    pm = {
        "schema": "pattern_memory_eval_v1",
        "pattern_outcome_stats_v1": {"schema": "pattern_outcome_stats_v1", "count": 1, "avg_pnl": 1.0},
    }
    ps = {"schema": "perps_state_model_v1", "volatility_state": "normal_volatility", "trend_state": "neutral"}
    risk = {"schema": "risk_inputs_v1", "invalidation_condition_v1": "x"}
    out = compute_expected_value_risk_cost_v1(
        perps_state_model_v1=ps,
        pattern_memory_eval_v1=pm,
        risk_inputs_v1=risk,
    )
    assert out["schema"] == SCHEMA_EXPECTED_VALUE_RISK_COST_V1
    assert out["available_v1"] is False
    assert out["preferred_action_v1"] == "not_available_v1"
    assert "insufficient_sample_v1" in (out.get("reason_codes_v1") or [])
    assert compute_ev_score_adjustment_v1(expected_value_risk_cost_v1=out, synthesized_action_v1="enter_long") == 0.0


def test_available_ev_paths_and_adjustment() -> None:
    pm = {
        "schema": "pattern_memory_eval_v1",
        "pattern_outcome_stats_v1": {
            "schema": "pattern_outcome_stats_v1",
            "count": 5,
            "avg_pnl": 25.0,
            "wins_total_fraction_v1": 0.6,
        },
    }
    ps = {
        "schema": "perps_state_model_v1",
        "volatility_state": "high_volatility",
        "trend_state": "bullish_trend",
    }
    risk = {"invalidation_condition_v1": "ic"}
    out = compute_expected_value_risk_cost_v1(
        perps_state_model_v1=ps,
        pattern_memory_eval_v1=pm,
        risk_inputs_v1=risk,
    )
    assert out["available_v1"] is True
    assert out["risk_costs_v1"]["volatility_penalty_v1"] > 0
    assert out["risk_costs_v1"]["funding_cost_v1"] == "not_available_v1"
    adj = compute_ev_score_adjustment_v1(
        expected_value_risk_cost_v1=out,
        synthesized_action_v1=str(out.get("preferred_action_v1") or "no_trade"),
    )
    assert -0.12 <= adj <= 0.12
