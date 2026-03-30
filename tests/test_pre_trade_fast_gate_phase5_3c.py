"""Phase 5.3c — Pre-trade fast gate tests.

Tests cover:
  - PreTradeGateV1 artifact structure (immutability, serialization)
  - run_pre_trade_fast_gate() across all three gate outcomes (allowed, downgraded, skipped)
  - Tier-aligned cost / EV / sizing thresholds (tier_1 / tier_2 / tier_3)
  - Abstain propagation from strategy evaluation errors
  - Uncertainty score from confidence and optional simulation abstain ratio
  - Capped sizing within tier limits
  - Determinism: same evaluation + same simulation = same gate result
  - Separation: gate is read-only, no execution, no tier escalation
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.participant_scope import ParticipantScope
from market_data.strategy_eval import STRATEGY_VERSION, StrategyEvaluationV1
from market_data.backtest_simulation import SimulationRunV1
from market_data.pre_trade_fast_gate import (
    GATE_OUTCOMES,
    GATE_VERSION,
    TIER_COST_BPS,
    TIER_EV_ALLOW_FLOOR,
    TIER_SIZE_CAP,
    UNCERTAINTY_DOWNGRADE,
    PreTradeGateV1,
    run_pre_trade_fast_gate,
    assert_strategy_version_matches,
)


def _scope(**overrides) -> ParticipantScope:
    d = dict(
        participant_id="sean",
        participant_type="human",
        account_id="acct_001",
        wallet_context="wallet_main",
        risk_tier="tier_2",
        interaction_path="telegram",
    )
    d.update(overrides)
    return ParticipantScope(**d)


def _eval(
    outcome: str = "long_bias",
    confidence: float = 0.85,
    spread_pct: float = 0.0025,
    tier: str = "tier_2",
    error: str | None = None,
    abstain_reason: str | None = None,
) -> StrategyEvaluationV1:
    scope = _scope(risk_tier=tier)
    return StrategyEvaluationV1(
        participant_scope=scope,
        symbol="SOL-USD",
        strategy_version=STRATEGY_VERSION,
        evaluation_outcome=outcome,
        confidence=confidence,
        abstain_reason=abstain_reason,
        gate_state="ok",
        primary_price=150.0,
        comparator_price=150.0 + (spread_pct * 150.0),
        spread_pct=spread_pct,
        tier_thresholds_used={"min_confidence": 0.4, "max_spread_pct": 0.004, "signal_spread_pct": 0.0003},
        evaluated_at="2026-03-27T00:00:00+00:00",
        error=error,
    )


def _sim(abstain_count: int = 0, sample_count: int = 10) -> SimulationRunV1:
    return SimulationRunV1(
        participant_scope=_scope(),
        symbol="SOL-USD",
        strategy_version=STRATEGY_VERSION,
        simulation_version="stored_data_backtest_v1",
        sample_count=sample_count,
        window_first_inserted_at="2026-03-26T00:00:00+00:00",
        window_last_inserted_at="2026-03-26T10:00:00+00:00",
        outcome_counts={"long_bias": sample_count - abstain_count, "abstain": abstain_count},
        abstain_count=abstain_count,
        skip_count=0,
        mean_confidence_non_abstain=0.8 if sample_count > abstain_count else None,
        run_at="2026-03-27T00:00:00+00:00",
        error=None,
    )


def test_gate_version_constant():
    assert GATE_VERSION == "pre_trade_fast_gate_v1"


def test_strategy_version_alignment():
    assert_strategy_version_matches()


def test_gate_outcomes_set():
    assert GATE_OUTCOMES == {"allowed", "downgraded", "skipped"}


def test_allowed_outcome_tier2():
    ev = _eval(outcome="long_bias", confidence=0.85, spread_pct=0.0025, tier="tier_2")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.gate_outcome == "allowed"
    assert g.abstain is False
    assert g.capped_size_fraction > 0.0
    assert g.capped_size_fraction <= TIER_SIZE_CAP["tier_2"]
    assert g.expected_value_after_costs is not None
    assert g.expected_value_after_costs > 0.0
    assert g.schema_version == "pre_trade_gate_v1"


def test_skipped_on_abstain_evaluation():
    ev = _eval(outcome="abstain", confidence=0.0, spread_pct=0.0, abstain_reason="no_tick_data")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.gate_outcome == "skipped"
    assert g.abstain is True
    assert g.capped_size_fraction == 0.0


def test_skipped_on_neutral_evaluation():
    ev = _eval(outcome="neutral", confidence=0.5, spread_pct=0.0001)
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.gate_outcome == "skipped"
    assert g.abstain is True


def test_skipped_on_evaluation_error():
    ev = _eval(error="market_data_error:no_db")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.gate_outcome == "skipped"
    assert g.abstain is True
    assert "strategy_evaluation_error" in (g.abstain_reason or "")


def test_skipped_on_negative_ev():
    ev = _eval(outcome="long_bias", confidence=0.3, spread_pct=0.0005, tier="tier_2")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.gate_outcome == "skipped"
    assert g.abstain is True


def test_skipped_on_unknown_tier():
    ev = _eval(tier="tier_99")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.gate_outcome == "skipped"
    assert "unknown_risk_tier" in (g.abstain_reason or "")


def test_downgraded_on_high_uncertainty():
    ev = _eval(outcome="long_bias", confidence=0.45, spread_pct=0.003, tier="tier_2")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.gate_outcome in {"downgraded", "skipped"}
    if g.gate_outcome == "downgraded":
        assert g.capped_size_fraction > 0.0
        assert g.capped_size_fraction <= TIER_SIZE_CAP["tier_2"]


def test_simulation_raises_uncertainty():
    ev = _eval(outcome="long_bias", confidence=0.85, spread_pct=0.0025, tier="tier_2")
    sim = _sim(abstain_count=8, sample_count=10)
    g = run_pre_trade_fast_gate(ev, simulation=sim, gated_at="2026-03-27T00:00:00+00:00")
    assert g.simulation_abstain_ratio == 0.8
    assert g.uncertainty_score >= 0.8
    assert g.gate_outcome in {"downgraded", "allowed"}


def test_determinism():
    ev = _eval()
    g1 = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    g2 = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g1.to_dict() == g2.to_dict()


def test_immutability():
    ev = _eval()
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    with pytest.raises(Exception):
        g.gate_outcome = "hacked"  # type: ignore[misc]


def test_tier1_sizing_cap():
    ev = _eval(outcome="long_bias", confidence=0.9, spread_pct=0.001, tier="tier_1")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.capped_size_fraction <= TIER_SIZE_CAP["tier_1"]


def test_tier3_sizing_cap():
    ev = _eval(outcome="short_bias", confidence=0.8, spread_pct=0.005, tier="tier_3")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.capped_size_fraction <= TIER_SIZE_CAP["tier_3"]


def test_to_dict_contains_required_fields():
    ev = _eval()
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    d = g.to_dict()
    required = [
        "participant_scope", "symbol", "strategy_version", "gate_version",
        "expected_value_after_costs", "uncertainty_score", "abstain",
        "abstain_reason", "capped_size_fraction", "gate_outcome", "summary",
        "evaluation_outcome", "confidence", "edge_bps_before_costs",
        "cost_bps_applied", "simulation_abstain_ratio", "gated_at",
        "schema_version",
    ]
    for field in required:
        assert field in d, f"missing field: {field}"


def test_no_tier_escalation():
    ev = _eval(tier="tier_1")
    g = run_pre_trade_fast_gate(ev, gated_at="2026-03-27T00:00:00+00:00")
    assert g.participant_scope.risk_tier == "tier_1"
