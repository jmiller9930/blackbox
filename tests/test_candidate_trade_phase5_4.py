"""Phase 5.4 — candidate trade artifact (v1)."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.candidate_trade import (
    CANDIDATE_TRADE_VERSION,
    CandidateTradeV1,
    build_candidate_trade_v1,
    validate_candidate_trade_v1,
)
from market_data.participant_scope import ParticipantScope
from market_data.pre_trade_fast_gate import PreTradeGateV1, run_pre_trade_fast_gate
from market_data.strategy_eval import STRATEGY_VERSION, StrategyEvaluationV1
from market_data.strategy_selection import select_tier_aligned_strategy


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


def _eval_long(tier: str = "tier_2") -> StrategyEvaluationV1:
    scope = _scope(risk_tier=tier)
    return StrategyEvaluationV1(
        participant_scope=scope,
        symbol="SOL-USD",
        strategy_version=STRATEGY_VERSION,
        evaluation_outcome="long_bias",
        confidence=0.85,
        abstain_reason=None,
        gate_state="ok",
        primary_price=150.0,
        comparator_price=151.0,
        spread_pct=0.0066,
        tier_thresholds_used={"min_confidence": 0.4, "max_spread_pct": 0.004, "signal_spread_pct": 0.0003},
        evaluated_at="2026-03-30T12:00:00+00:00",
        error=None,
    )


def _gate_for(eval_v: StrategyEvaluationV1) -> PreTradeGateV1:
    return run_pre_trade_fast_gate(eval_v, simulation=None, gated_at="2026-03-30T12:01:00+00:00")


def test_build_from_selection_and_gate_deterministic() -> None:
    ev = _eval_long()
    gate = _gate_for(ev)
    sel = select_tier_aligned_strategy(ev, gate=gate, selected_at="2026-03-30T12:02:00+00:00")
    assert sel.selection_outcome == "selected"
    c = build_candidate_trade_v1(
        ev,
        sel,
        gate=gate,
        expires_at_iso="2026-03-30T13:00:00+00:00",
        candidate_built_at="2026-03-30T12:03:00+00:00",
    )
    assert c.side == "long"
    assert c.symbol == "SOL-USD"
    assert c.schema_version == CANDIDATE_TRADE_VERSION
    assert c.notional_fraction == gate.capped_size_fraction
    assert c.tier_risk_cap_fraction == 0.5
    assert c.strategy_profile == "balanced_spread_profile_v1"
    validate_candidate_trade_v1(c)


def test_serialization_stable_sorted_json() -> None:
    ev = _eval_long()
    gate = _gate_for(ev)
    sel = select_tier_aligned_strategy(ev, gate=gate, selected_at="2026-03-30T12:02:00+00:00")
    c = build_candidate_trade_v1(
        ev,
        sel,
        gate=gate,
        expires_at_iso="2026-03-30T13:00:00+00:00",
        candidate_built_at="2026-03-30T12:03:00+00:00",
    )
    d = c.to_dict()
    a = json.dumps(d, sort_keys=True, separators=(",", ":"))
    b = json.dumps(c.to_dict(), sort_keys=True, separators=(",", ":"))
    assert a == b


def test_rejects_selection_skipped() -> None:
    ev = replace(_eval_long(), evaluation_outcome="neutral")
    sel = select_tier_aligned_strategy(ev, gate=None, selected_at="2026-03-30T12:02:00+00:00")
    assert sel.selection_outcome == "skipped"
    with pytest.raises(ValueError, match="not_selected"):
        build_candidate_trade_v1(
            ev,
            sel,
            gate=None,
            expires_at_iso="2026-03-30T13:00:00+00:00",
            candidate_built_at="2026-03-30T12:03:00+00:00",
            notional_fraction=0.1,
        )


def test_rejects_tier_mutation_on_selection() -> None:
    ev = _eval_long()
    gate = _gate_for(ev)
    sel = select_tier_aligned_strategy(ev, gate=gate, selected_at="2026-03-30T12:02:00+00:00")
    bad = replace(sel, selected_risk_tier="tier_3")
    with pytest.raises(ValueError, match="tier_mutation"):
        build_candidate_trade_v1(
            ev,
            bad,
            gate=gate,
            expires_at_iso="2026-03-30T13:00:00+00:00",
            candidate_built_at="2026-03-30T12:03:00+00:00",
        )


def test_validate_rejects_notional_above_cap() -> None:
    scope = _scope()
    c = CandidateTradeV1(
        participant_scope=scope,
        symbol="SOL-USD",
        side="long",
        notional_fraction=0.99,
        tier_risk_cap_fraction=0.5,
        strategy_profile="balanced_spread_profile_v1",
        strategy_version=STRATEGY_VERSION,
        selection_version="tier_aligned_strategy_selection_v1",
        evaluation_outcome="long_bias",
        selection_outcome="selected",
        gate_outcome="allowed",
        expires_at_iso="2026-03-30T13:00:00+00:00",
        source_evaluated_at="2026-03-30T12:00:00+00:00",
        source_selected_at="2026-03-30T12:02:00+00:00",
        source_gated_at="2026-03-30T12:01:00+00:00",
        candidate_built_at="2026-03-30T12:03:00+00:00",
    )
    with pytest.raises(ValueError, match="notional_out_of_envelope"):
        validate_candidate_trade_v1(c)


def test_build_without_gate_explicit_notional() -> None:
    ev = _eval_long()
    sel = select_tier_aligned_strategy(ev, gate=None, selected_at="2026-03-30T12:02:00+00:00")
    c = build_candidate_trade_v1(
        ev,
        sel,
        gate=None,
        notional_fraction=0.25,
        expires_at_iso="2026-03-30T13:00:00+00:00",
        candidate_built_at="2026-03-30T12:03:00+00:00",
    )
    assert c.notional_fraction == 0.25
    assert c.gate_outcome is None
    assert c.source_gated_at is None
