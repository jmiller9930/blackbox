"""Phase 5.3c — Pre-trade fast gate.

Consumes :class:`StrategyEvaluationV1` (Phase 5.3a) and optionally
:class:`SimulationRunV1` (Phase 5.3b) to produce a deterministic
:class:`PreTradeGateV1` artifact.  Strategy-side gating only: no Billy, no
approval intents, no venue or account actions.  ``risk_tier`` on the evaluation
scope is never assigned or escalated here; thresholds stay within the selected
tier.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from market_data.backtest_simulation import SimulationRunV1
from market_data.strategy_eval import STRATEGY_VERSION, StrategyEvaluationV1, TIER_THRESHOLDS

GATE_VERSION = "pre_trade_fast_gate_v1"

# Estimated round-trip friction (bps) by tier — conservative, tier-scoped only.
TIER_COST_BPS: dict[str, float] = {
    "tier_1": 8.0,
    "tier_2": 12.0,
    "tier_3": 18.0,
}

# Minimum normalized EV (after costs, confidence-weighted) to consider "full"
# allow vs downgrade band.  Values are small fractions (not dollar PnL).
TIER_EV_ALLOW_FLOOR: dict[str, float] = {
    "tier_1": 0.00006,
    "tier_2": 0.00004,
    "tier_3": 0.000025,
}

# Max fractional sizing cap within tier (operator notional is out of scope).
TIER_SIZE_CAP: dict[str, float] = {
    "tier_1": 0.25,
    "tier_2": 0.5,
    "tier_3": 1.0,
}

GATE_OUTCOMES = frozenset({"allowed", "downgraded", "skipped"})

UNCERTAINTY_DOWNGRADE = 0.42


@dataclass(frozen=True)
class PreTradeGateV1:
    """Structured pre-trade gate artifact for a single evaluated candidate."""

    participant_scope: Any  # ParticipantScope — avoid circular import in typing
    symbol: str
    strategy_version: str
    gate_version: str
    expected_value_after_costs: float | None
    uncertainty_score: float
    abstain: bool
    abstain_reason: str | None
    capped_size_fraction: float
    gate_outcome: str
    summary: str
    evaluation_outcome: str
    confidence: float
    edge_bps_before_costs: float | None
    cost_bps_applied: float | None
    simulation_abstain_ratio: float | None
    gated_at: str
    error: str | None = None
    schema_version: str = "pre_trade_gate_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_ev_and_edge(
    evaluation: StrategyEvaluationV1,
) -> tuple[float | None, float | None, float | None]:
    """Return (ev_after_costs, edge_bps, cost_bps) from evaluation fields."""
    tier = evaluation.participant_scope.risk_tier
    cost_bps = TIER_COST_BPS.get(tier)
    if cost_bps is None:
        return None, None, None
    sp = evaluation.spread_pct
    if sp is None:
        return None, None, cost_bps
    edge_bps = abs(float(sp)) * 10000.0
    raw_ev_bps = edge_bps - cost_bps
    conf = float(evaluation.confidence)
    ev = (raw_ev_bps / 10000.0) * conf
    return round(ev, 10), round(edge_bps, 6), cost_bps


def _simulation_abstain_ratio(sim: SimulationRunV1 | None) -> float | None:
    if sim is None or sim.error is not None:
        return None
    n = sim.sample_count
    if n <= 0:
        return None
    return round(sim.abstain_count / n, 6)


def run_pre_trade_fast_gate(
    evaluation: StrategyEvaluationV1,
    *,
    simulation: SimulationRunV1 | None = None,
    gated_at: str | None = None,
) -> PreTradeGateV1:
    """Run the fast gate on a :class:`StrategyEvaluationV1` candidate.

    Deterministic given the same evaluation and optional simulation aggregate.
    Read-only.
    """
    ts = gated_at or _utc_now()
    scope = evaluation.participant_scope
    sym = evaluation.symbol
    tier = scope.risk_tier

    sim_ratio = _simulation_abstain_ratio(simulation)

    if evaluation.error is not None:
        return PreTradeGateV1(
            participant_scope=scope,
            symbol=sym,
            strategy_version=evaluation.strategy_version,
            gate_version=GATE_VERSION,
            expected_value_after_costs=None,
            uncertainty_score=1.0,
            abstain=True,
            abstain_reason="strategy_evaluation_error",
            capped_size_fraction=0.0,
            gate_outcome="skipped",
            summary="Skipped: strategy evaluation carried an error field.",
            evaluation_outcome=evaluation.evaluation_outcome,
            confidence=float(evaluation.confidence),
            edge_bps_before_costs=None,
            cost_bps_applied=None,
            simulation_abstain_ratio=sim_ratio,
            gated_at=ts,
            error=None,
        )

    if tier not in TIER_THRESHOLDS:
        return PreTradeGateV1(
            participant_scope=scope,
            symbol=sym,
            strategy_version=evaluation.strategy_version,
            gate_version=GATE_VERSION,
            expected_value_after_costs=None,
            uncertainty_score=1.0,
            abstain=True,
            abstain_reason="unknown_risk_tier",
            capped_size_fraction=0.0,
            gate_outcome="skipped",
            summary="Skipped: risk tier has no tier-local gate table entry.",
            evaluation_outcome=evaluation.evaluation_outcome,
            confidence=float(evaluation.confidence),
            edge_bps_before_costs=None,
            cost_bps_applied=TIER_COST_BPS.get(tier),
            simulation_abstain_ratio=sim_ratio,
            gated_at=ts,
        )

    ev_after, edge_bps, cost_bps = _compute_ev_and_edge(evaluation)
    base_uncertainty = max(0.0, min(1.0, 1.0 - float(evaluation.confidence)))
    if sim_ratio is not None:
        uncertainty = max(base_uncertainty, sim_ratio)
    else:
        uncertainty = base_uncertainty
    uncertainty = round(min(1.0, uncertainty), 6)

    outcome = evaluation.evaluation_outcome
    if outcome in ("abstain", "neutral"):
        reason = evaluation.abstain_reason or (
            "neutral_bias" if outcome == "neutral" else "abstain"
        )
        return PreTradeGateV1(
            participant_scope=scope,
            symbol=sym,
            strategy_version=evaluation.strategy_version,
            gate_version=GATE_VERSION,
            expected_value_after_costs=ev_after,
            uncertainty_score=uncertainty,
            abstain=True,
            abstain_reason=reason,
            capped_size_fraction=0.0,
            gate_outcome="skipped",
            summary=(
                "Skipped: no directional candidate (neutral or abstain from "
                f"strategy evaluation: {reason})."
            ),
            evaluation_outcome=outcome,
            confidence=float(evaluation.confidence),
            edge_bps_before_costs=edge_bps,
            cost_bps_applied=cost_bps,
            simulation_abstain_ratio=sim_ratio,
            gated_at=ts,
        )

    if outcome not in ("long_bias", "short_bias"):
        return PreTradeGateV1(
            participant_scope=scope,
            symbol=sym,
            strategy_version=evaluation.strategy_version,
            gate_version=GATE_VERSION,
            expected_value_after_costs=ev_after,
            uncertainty_score=uncertainty,
            abstain=True,
            abstain_reason="unexpected_evaluation_outcome",
            capped_size_fraction=0.0,
            gate_outcome="skipped",
            summary=f"Skipped: unrecognized evaluation outcome {outcome!r}.",
            evaluation_outcome=outcome,
            confidence=float(evaluation.confidence),
            edge_bps_before_costs=edge_bps,
            cost_bps_applied=cost_bps,
            simulation_abstain_ratio=sim_ratio,
            gated_at=ts,
        )

    if ev_after is None or ev_after <= 0.0:
        return PreTradeGateV1(
            participant_scope=scope,
            symbol=sym,
            strategy_version=evaluation.strategy_version,
            gate_version=GATE_VERSION,
            expected_value_after_costs=ev_after,
            uncertainty_score=uncertainty,
            abstain=True,
            abstain_reason="ev_after_costs_non_positive",
            capped_size_fraction=0.0,
            gate_outcome="skipped",
            summary="Skipped: expected value after costs is not positive at this tier.",
            evaluation_outcome=outcome,
            confidence=float(evaluation.confidence),
            edge_bps_before_costs=edge_bps,
            cost_bps_applied=cost_bps,
            simulation_abstain_ratio=sim_ratio,
            gated_at=ts,
        )

    allow_floor = TIER_EV_ALLOW_FLOOR.get(tier, 0.0)
    cap = TIER_SIZE_CAP.get(tier, 0.0)
    ev_ratio = ev_after / allow_floor if allow_floor > 0 else 0.0
    size_raw = cap * float(evaluation.confidence) * min(1.0, max(0.0, ev_ratio))
    size_raw = round(min(cap, max(0.0, size_raw)), 6)

    strong_ev = ev_after >= allow_floor
    low_uncertainty = uncertainty <= UNCERTAINTY_DOWNGRADE

    if strong_ev and low_uncertainty:
        gate_outcome = "allowed"
        summary = (
            "Allowed: EV after costs clears tier floor and uncertainty is within "
            "the downgrade band."
        )
        capped = size_raw
        abstain = False
        abstain_reason = None
    elif ev_after > 0.0:
        gate_outcome = "downgraded"
        summary = (
            "Downgraded: directional signal survives costs but size is capped "
            "(high uncertainty or EV below full-allow threshold for tier)."
        )
        capped = round(size_raw * 0.5, 6)
        abstain = False
        abstain_reason = None
    else:
        gate_outcome = "skipped"
        summary = "Skipped: EV after costs did not clear internal tier checks."
        capped = 0.0
        abstain = True
        abstain_reason = "gate_internal_skip"

    return PreTradeGateV1(
        participant_scope=scope,
        symbol=sym,
        strategy_version=evaluation.strategy_version,
        gate_version=GATE_VERSION,
        expected_value_after_costs=ev_after,
        uncertainty_score=uncertainty,
        abstain=abstain,
        abstain_reason=abstain_reason,
        capped_size_fraction=capped,
        gate_outcome=gate_outcome,
        summary=summary,
        evaluation_outcome=outcome,
        confidence=float(evaluation.confidence),
        edge_bps_before_costs=edge_bps,
        cost_bps_applied=cost_bps,
        simulation_abstain_ratio=sim_ratio,
        gated_at=ts,
    )


def assert_strategy_version_matches() -> None:
    """Test helper: gate module expects 5.3a strategy version string alignment."""
    assert STRATEGY_VERSION == "deterministic_spread_v1"
