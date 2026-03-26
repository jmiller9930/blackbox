"""Phase 5.3a — Deterministic strategy evaluation contract.

Reads stored market data only (via Phase 5.2a scoped-reader API) and emits a
structured evaluation artifact.  This is an evaluation surface — not execution.
No Billy behavior, no Layer 4 intent, no live venue actions.

The v1 strategy uses the primary/comparator price spread from the latest stored
tick, gated by data quality and tier-aligned thresholds.  The evaluation is
fully deterministic given the same stored tick and participant scope.

risk_tier drives threshold selection but is never assigned or escalated here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_data.participant_scope import ParticipantScope, validate_participant_scope
from market_data.read_contracts import MarketDataReadContractV1, validate_market_data_read_contract
from market_data.scoped_reader import ScopedMarketDataSnapshot, read_latest_scoped_tick

STRATEGY_VERSION = "deterministic_spread_v1"

EVALUATION_OUTCOMES = frozenset({
    "long_bias",
    "short_bias",
    "neutral",
    "abstain",
})

TIER_THRESHOLDS: dict[str, dict[str, float]] = {
    "tier_1": {
        "min_confidence": 0.6,
        "max_spread_pct": 0.002,
        "signal_spread_pct": 0.0005,
    },
    "tier_2": {
        "min_confidence": 0.4,
        "max_spread_pct": 0.004,
        "signal_spread_pct": 0.0003,
    },
    "tier_3": {
        "min_confidence": 0.25,
        "max_spread_pct": 0.006,
        "signal_spread_pct": 0.0002,
    },
}


@dataclass(frozen=True)
class StrategyEvaluationV1:
    """Structured evaluation artifact for a single-symbol strategy pass.

    Immutable.  Carries participant scope, strategy metadata, and the
    deterministic evaluation outcome.  This artifact is the input to
    future approval routing — it never triggers execution by itself.
    """

    participant_scope: ParticipantScope
    symbol: str
    strategy_version: str
    evaluation_outcome: str
    confidence: float
    abstain_reason: str | None
    gate_state: str | None
    primary_price: float | None
    comparator_price: float | None
    spread_pct: float | None
    tier_thresholds_used: dict[str, float] | None
    evaluated_at: str
    error: str | None = None
    schema_version: str = "strategy_evaluation_v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _compute_spread_pct(
    primary: float | None, comparator: float | None
) -> float | None:
    if primary is None or comparator is None:
        return None
    if primary <= 0 or comparator <= 0:
        return None
    mid = (primary + comparator) / 2.0
    return (primary - comparator) / mid


def _evaluate_from_snapshot(
    snapshot: ScopedMarketDataSnapshot,
    scope: ParticipantScope,
    symbol: str,
    evaluated_at: str,
) -> StrategyEvaluationV1:
    """Core deterministic evaluation logic on a valid snapshot."""

    thresholds = TIER_THRESHOLDS.get(scope.risk_tier)
    if thresholds is None:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason=f"unknown_risk_tier:{scope.risk_tier}",
            gate_state=snapshot.gate_state,
            primary_price=None,
            comparator_price=None,
            spread_pct=None,
            tier_thresholds_used=None,
            evaluated_at=evaluated_at,
        )

    tick = snapshot.tick
    if tick is None:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason="no_tick_data",
            gate_state=snapshot.gate_state,
            primary_price=None,
            comparator_price=None,
            spread_pct=None,
            tier_thresholds_used=dict(thresholds),
            evaluated_at=evaluated_at,
        )

    gate = snapshot.gate_state
    if gate == "blocked":
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason="gate_blocked",
            gate_state=gate,
            primary_price=tick.get("primary_price"),
            comparator_price=tick.get("comparator_price"),
            spread_pct=None,
            tier_thresholds_used=dict(thresholds),
            evaluated_at=evaluated_at,
        )

    primary_price = tick.get("primary_price")
    comparator_price = tick.get("comparator_price")
    spread_pct = _compute_spread_pct(primary_price, comparator_price)

    if spread_pct is None:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason="insufficient_price_data",
            gate_state=gate,
            primary_price=primary_price,
            comparator_price=comparator_price,
            spread_pct=None,
            tier_thresholds_used=dict(thresholds),
            evaluated_at=evaluated_at,
        )

    abs_spread = abs(spread_pct)
    max_spread = thresholds["max_spread_pct"]
    signal_threshold = thresholds["signal_spread_pct"]
    min_confidence = thresholds["min_confidence"]

    if abs_spread > max_spread:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason="spread_exceeds_tier_limit",
            gate_state=gate,
            primary_price=primary_price,
            comparator_price=comparator_price,
            spread_pct=spread_pct,
            tier_thresholds_used=dict(thresholds),
            evaluated_at=evaluated_at,
        )

    gate_penalty = 0.15 if gate == "degraded" else 0.0
    spread_ratio = abs_spread / max_spread if max_spread > 0 else 0.0
    raw_confidence = max(0.0, 1.0 - spread_ratio - gate_penalty)
    confidence = round(raw_confidence, 4)

    if abs_spread < signal_threshold:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="neutral",
            confidence=confidence,
            abstain_reason=None,
            gate_state=gate,
            primary_price=primary_price,
            comparator_price=comparator_price,
            spread_pct=spread_pct,
            tier_thresholds_used=dict(thresholds),
            evaluated_at=evaluated_at,
        )

    if confidence < min_confidence:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=confidence,
            abstain_reason="confidence_below_tier_minimum",
            gate_state=gate,
            primary_price=primary_price,
            comparator_price=comparator_price,
            spread_pct=spread_pct,
            tier_thresholds_used=dict(thresholds),
            evaluated_at=evaluated_at,
        )

    outcome = "long_bias" if spread_pct < 0 else "short_bias"

    return StrategyEvaluationV1(
        participant_scope=scope,
        symbol=symbol,
        strategy_version=STRATEGY_VERSION,
        evaluation_outcome=outcome,
        confidence=confidence,
        abstain_reason=None,
        gate_state=gate,
        primary_price=primary_price,
        comparator_price=comparator_price,
        spread_pct=spread_pct,
        tier_thresholds_used=dict(thresholds),
        evaluated_at=evaluated_at,
    )


def evaluate_strategy_from_read_contract(
    contract: MarketDataReadContractV1,
    *,
    db_path: Path | None = None,
) -> StrategyEvaluationV1:
    """Phase 5.3a entry point aligned with Phase 5.2a read contracts.

    Validates ``MarketDataReadContractV1``, then runs :func:`evaluate_strategy`
    on the embedded participant scope and ``market_symbol``. Read-only.
    """
    evaluated_at = datetime.now(timezone.utc).isoformat()
    try:
        validate_market_data_read_contract(contract)
    except ValueError as exc:
        scope = contract.to_participant_scope()
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=str(contract.market_symbol or "").strip() or "?",
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason="market_data_read_contract_invalid",
            gate_state=None,
            primary_price=None,
            comparator_price=None,
            spread_pct=None,
            tier_thresholds_used=None,
            evaluated_at=evaluated_at,
            error=f"market_data_read_contract_invalid:{exc}",
        )
    scope = contract.to_participant_scope()
    return evaluate_strategy(scope, contract.market_symbol.strip(), db_path=db_path)


def evaluate_strategy(
    scope: ParticipantScope,
    symbol: str = "SOL-USD",
    *,
    db_path: Path | None = None,
) -> StrategyEvaluationV1:
    """Run a deterministic strategy evaluation for a single symbol.

    1. Validates participant scope.
    2. Reads the latest stored tick via the Phase 5.2a scoped-reader API.
    3. Applies the deterministic spread-based v1 strategy.
    4. Returns a structured StrategyEvaluationV1 artifact.

    Read-only.  No writes.  No execution intent.  No tier escalation.
    """
    evaluated_at = datetime.now(timezone.utc).isoformat()

    try:
        validate_participant_scope(scope)
    except ValueError as exc:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason="scope_validation_failed",
            gate_state=None,
            primary_price=None,
            comparator_price=None,
            spread_pct=None,
            tier_thresholds_used=None,
            evaluated_at=evaluated_at,
            error=f"scope_validation_failed:{exc}",
        )

    snapshot = read_latest_scoped_tick(scope, symbol, db_path=db_path)

    if snapshot.error is not None:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason=f"market_data_error:{snapshot.error}",
            gate_state=snapshot.gate_state,
            primary_price=None,
            comparator_price=None,
            spread_pct=None,
            tier_thresholds_used=TIER_THRESHOLDS.get(scope.risk_tier),
            evaluated_at=evaluated_at,
            error=snapshot.error,
        )

    return _evaluate_from_snapshot(snapshot, scope, symbol, evaluated_at)
