"""Phase 5.3d — Tier-aligned strategy selection contract.

Builds an explicit, deterministic strategy-selection artifact from the existing
strategy evaluation and optional pre-trade fast gate surfaces. Selection stays
inside the participant-selected risk tier and never mixes, assigns, or
escalates tiers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from market_data.pre_trade_fast_gate import PreTradeGateV1
from market_data.strategy_eval import STRATEGY_VERSION, StrategyEvaluationV1, TIER_THRESHOLDS

SELECTION_VERSION = "tier_aligned_strategy_selection_v1"

TIER_STRATEGY_PROFILES: dict[str, str] = {
    "tier_1": "conservative_spread_profile_v1",
    "tier_2": "balanced_spread_profile_v1",
    "tier_3": "aggressive_spread_profile_v1",
}

SELECTION_OUTCOMES = frozenset({"selected", "skipped"})


@dataclass(frozen=True)
class StrategySelectionV1:
    """Explicit strategy-selection artifact for the selected tier."""

    participant_scope: Any
    symbol: str
    strategy_version: str
    selection_version: str
    selected_risk_tier: str
    selected_strategy_profile: str | None
    selection_outcome: str
    selection_reason: str
    evaluation_outcome: str
    gate_outcome: str | None
    selected_at: str
    error: str | None = None
    schema_version: str = "strategy_selection_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def select_tier_aligned_strategy(
    evaluation: StrategyEvaluationV1,
    *,
    gate: PreTradeGateV1 | None = None,
    selected_at: str | None = None,
) -> StrategySelectionV1:
    """Select the explicit tier-local strategy profile for a candidate.

    Deterministic given the same evaluation and optional gate. Read-only.
    """
    ts = selected_at or _utc_now()
    scope = evaluation.participant_scope
    tier = scope.risk_tier
    symbol = evaluation.symbol

    if evaluation.error is not None:
        return StrategySelectionV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=evaluation.strategy_version,
            selection_version=SELECTION_VERSION,
            selected_risk_tier=tier,
            selected_strategy_profile=None,
            selection_outcome="skipped",
            selection_reason="strategy_evaluation_error",
            evaluation_outcome=evaluation.evaluation_outcome,
            gate_outcome=gate.gate_outcome if gate else None,
            selected_at=ts,
        )

    if tier not in TIER_THRESHOLDS or tier not in TIER_STRATEGY_PROFILES:
        return StrategySelectionV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=evaluation.strategy_version,
            selection_version=SELECTION_VERSION,
            selected_risk_tier=tier,
            selected_strategy_profile=None,
            selection_outcome="skipped",
            selection_reason="unknown_risk_tier",
            evaluation_outcome=evaluation.evaluation_outcome,
            gate_outcome=gate.gate_outcome if gate else None,
            selected_at=ts,
        )

    if gate is not None:
        gate_scope = gate.participant_scope
        if gate_scope.risk_tier != tier:
            return StrategySelectionV1(
                participant_scope=scope,
                symbol=symbol,
                strategy_version=evaluation.strategy_version,
                selection_version=SELECTION_VERSION,
                selected_risk_tier=tier,
                selected_strategy_profile=None,
                selection_outcome="skipped",
                selection_reason="gate_risk_tier_mismatch",
                evaluation_outcome=evaluation.evaluation_outcome,
                gate_outcome=gate.gate_outcome,
                selected_at=ts,
                error="tier_alignment_mismatch",
            )
        if gate.symbol != symbol:
            return StrategySelectionV1(
                participant_scope=scope,
                symbol=symbol,
                strategy_version=evaluation.strategy_version,
                selection_version=SELECTION_VERSION,
                selected_risk_tier=tier,
                selected_strategy_profile=None,
                selection_outcome="skipped",
                selection_reason="gate_symbol_mismatch",
                evaluation_outcome=evaluation.evaluation_outcome,
                gate_outcome=gate.gate_outcome,
                selected_at=ts,
                error="symbol_alignment_mismatch",
            )
        if gate.strategy_version != evaluation.strategy_version:
            return StrategySelectionV1(
                participant_scope=scope,
                symbol=symbol,
                strategy_version=evaluation.strategy_version,
                selection_version=SELECTION_VERSION,
                selected_risk_tier=tier,
                selected_strategy_profile=None,
                selection_outcome="skipped",
                selection_reason="gate_strategy_version_mismatch",
                evaluation_outcome=evaluation.evaluation_outcome,
                gate_outcome=gate.gate_outcome,
                selected_at=ts,
                error="strategy_alignment_mismatch",
            )
        if gate.gate_outcome == "skipped" or gate.abstain:
            return StrategySelectionV1(
                participant_scope=scope,
                symbol=symbol,
                strategy_version=evaluation.strategy_version,
                selection_version=SELECTION_VERSION,
                selected_risk_tier=tier,
                selected_strategy_profile=None,
                selection_outcome="skipped",
                selection_reason="gate_rejected_candidate",
                evaluation_outcome=evaluation.evaluation_outcome,
                gate_outcome=gate.gate_outcome,
                selected_at=ts,
            )

    if evaluation.evaluation_outcome not in ("long_bias", "short_bias"):
        return StrategySelectionV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=evaluation.strategy_version,
            selection_version=SELECTION_VERSION,
            selected_risk_tier=tier,
            selected_strategy_profile=None,
            selection_outcome="skipped",
            selection_reason="no_directional_candidate",
            evaluation_outcome=evaluation.evaluation_outcome,
            gate_outcome=gate.gate_outcome if gate else None,
            selected_at=ts,
        )

    return StrategySelectionV1(
        participant_scope=scope,
        symbol=symbol,
        strategy_version=STRATEGY_VERSION,
        selection_version=SELECTION_VERSION,
        selected_risk_tier=tier,
        selected_strategy_profile=TIER_STRATEGY_PROFILES[tier],
        selection_outcome="selected",
        selection_reason="tier_local_profile_selected",
        evaluation_outcome=evaluation.evaluation_outcome,
        gate_outcome=gate.gate_outcome if gate else None,
        selected_at=ts,
    )
