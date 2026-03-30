"""Phase 5.3d — tier-aligned strategy selection tests."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.backtest_simulation import SimulationRunV1
from market_data.participant_scope import ParticipantScope
from market_data.pre_trade_fast_gate import run_pre_trade_fast_gate
from market_data.strategy_eval import STRATEGY_VERSION, StrategyEvaluationV1
from market_data.strategy_selection import (
    SELECTION_OUTCOMES,
    SELECTION_VERSION,
    TIER_STRATEGY_PROFILES,
    StrategySelectionV1,
    select_tier_aligned_strategy,
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
    *,
    tier: str = "tier_2",
    outcome: str = "long_bias",
    confidence: float = 0.85,
    spread_pct: float = 0.0025,
    error: str | None = None,
) -> StrategyEvaluationV1:
    scope = _scope(risk_tier=tier)
    return StrategyEvaluationV1(
        participant_scope=scope,
        symbol="SOL-USD",
        strategy_version=STRATEGY_VERSION,
        evaluation_outcome=outcome,
        confidence=confidence,
        abstain_reason=None,
        gate_state="ok",
        primary_price=150.0,
        comparator_price=150.0 + (spread_pct * 150.0),
        spread_pct=spread_pct,
        tier_thresholds_used={"min_confidence": 0.4, "max_spread_pct": 0.004, "signal_spread_pct": 0.0003},
        evaluated_at="2026-03-27T00:00:00+00:00",
        error=error,
    )


def _sim() -> SimulationRunV1:
    return SimulationRunV1(
        participant_scope=_scope(),
        symbol="SOL-USD",
        strategy_version=STRATEGY_VERSION,
        simulation_version="stored_simulation_v1",
        sample_count=10,
        window_first_inserted_at="2026-03-27T00:00:00+00:00",
        window_last_inserted_at="2026-03-27T01:00:00+00:00",
        outcome_counts={"long_bias": 10},
        abstain_count=0,
        skip_count=0,
        mean_confidence_non_abstain=0.8,
        run_at="2026-03-27T01:00:00+00:00",
        error=None,
    )


def test_selection_version_constant():
    assert SELECTION_VERSION == "tier_aligned_strategy_selection_v1"


def test_selection_outcomes_set():
    assert SELECTION_OUTCOMES == {"selected", "skipped"}


def test_selected_profile_tier_1():
    sel = select_tier_aligned_strategy(_eval(tier="tier_1"), selected_at="2026-03-27T00:00:00+00:00")
    assert sel.selection_outcome == "selected"
    assert sel.selected_strategy_profile == TIER_STRATEGY_PROFILES["tier_1"]
    assert sel.selected_risk_tier == "tier_1"


def test_selected_profile_tier_3():
    sel = select_tier_aligned_strategy(_eval(tier="tier_3", outcome="short_bias", spread_pct=0.005), selected_at="2026-03-27T00:00:00+00:00")
    assert sel.selection_outcome == "selected"
    assert sel.selected_strategy_profile == TIER_STRATEGY_PROFILES["tier_3"]
    assert sel.selected_risk_tier == "tier_3"


def test_no_tier_escalation():
    sel = select_tier_aligned_strategy(_eval(tier="tier_1"), selected_at="2026-03-27T00:00:00+00:00")
    assert sel.participant_scope.risk_tier == "tier_1"
    assert sel.selected_risk_tier == "tier_1"


def test_skips_unknown_tier():
    sel = select_tier_aligned_strategy(_eval(tier="tier_99"), selected_at="2026-03-27T00:00:00+00:00")
    assert sel.selection_outcome == "skipped"
    assert sel.selection_reason == "unknown_risk_tier"


def test_skips_neutral_candidate():
    sel = select_tier_aligned_strategy(_eval(outcome="neutral"), selected_at="2026-03-27T00:00:00+00:00")
    assert sel.selection_outcome == "skipped"
    assert sel.selection_reason == "no_directional_candidate"


def test_skips_on_strategy_error():
    sel = select_tier_aligned_strategy(_eval(error="market_data_error"), selected_at="2026-03-27T00:00:00+00:00")
    assert sel.selection_outcome == "skipped"
    assert sel.selection_reason == "strategy_evaluation_error"


def test_gate_mismatch_does_not_fallback_cross_tier():
    evaluation = _eval(tier="tier_1")
    gate = run_pre_trade_fast_gate(_eval(tier="tier_3"), simulation=_sim(), gated_at="2026-03-27T00:00:00+00:00")
    sel = select_tier_aligned_strategy(evaluation, gate=gate, selected_at="2026-03-27T00:00:00+00:00")
    assert sel.selection_outcome == "skipped"
    assert sel.selection_reason == "gate_risk_tier_mismatch"
    assert sel.error == "tier_alignment_mismatch"


def test_gate_symbol_mismatch_blocks_selection():
    evaluation = _eval()
    gate = run_pre_trade_fast_gate(evaluation, simulation=_sim(), gated_at="2026-03-27T00:00:00+00:00")
    gate = replace(gate, symbol="BTC-USD")
    sel = select_tier_aligned_strategy(evaluation, gate=gate, selected_at="2026-03-27T00:00:00+00:00")
    assert sel.selection_outcome == "skipped"
    assert sel.selection_reason == "gate_symbol_mismatch"
    assert sel.error == "symbol_alignment_mismatch"


def test_gate_strategy_version_mismatch_blocks_selection():
    evaluation = _eval()
    gate = run_pre_trade_fast_gate(evaluation, simulation=_sim(), gated_at="2026-03-27T00:00:00+00:00")
    gate = replace(gate, strategy_version="strategy_v0")
    sel = select_tier_aligned_strategy(evaluation, gate=gate, selected_at="2026-03-27T00:00:00+00:00")
    assert sel.selection_outcome == "skipped"
    assert sel.selection_reason == "gate_strategy_version_mismatch"
    assert sel.error == "strategy_alignment_mismatch"


def test_gate_skipped_candidate_blocks_selection():
    evaluation = _eval(confidence=0.3, spread_pct=0.0005)
    gate = run_pre_trade_fast_gate(evaluation, gated_at="2026-03-27T00:00:00+00:00")
    sel = select_tier_aligned_strategy(evaluation, gate=gate, selected_at="2026-03-27T00:00:00+00:00")
    assert gate.gate_outcome == "skipped"
    assert sel.selection_outcome == "skipped"
    assert sel.selection_reason == "gate_rejected_candidate"


def test_determinism():
    evaluation = _eval()
    gate = run_pre_trade_fast_gate(evaluation, simulation=_sim(), gated_at="2026-03-27T00:00:00+00:00")
    s1 = select_tier_aligned_strategy(evaluation, gate=gate, selected_at="2026-03-27T00:00:00+00:00")
    s2 = select_tier_aligned_strategy(evaluation, gate=gate, selected_at="2026-03-27T00:00:00+00:00")
    assert s1.to_dict() == s2.to_dict()


def test_immutability():
    sel = select_tier_aligned_strategy(_eval(), selected_at="2026-03-27T00:00:00+00:00")
    with pytest.raises(Exception):
        sel.selection_outcome = "hacked"  # type: ignore[misc]


def test_to_dict_contains_required_fields():
    sel = select_tier_aligned_strategy(_eval(), selected_at="2026-03-27T00:00:00+00:00")
    d = sel.to_dict()
    for field in (
        "participant_scope",
        "symbol",
        "strategy_version",
        "selection_version",
        "selected_risk_tier",
        "selected_strategy_profile",
        "selection_outcome",
        "selection_reason",
        "evaluation_outcome",
        "gate_outcome",
        "selected_at",
        "schema_version",
    ):
        assert field in d
