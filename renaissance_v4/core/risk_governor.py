"""
risk_governor.py

Purpose:
Apply risk governance to fused directional decisions for RenaissanceV4.

Usage:
Used by the replay runner after the fusion engine has produced a directional result.

Version:
v1.0

Change History:
- v1.0 Initial Phase 5 implementation.
- v1.1 DV risk correction: tier thresholds and persistence compression aligned to observed effective-score
  distribution (diagnostic_risk_v1.md); see correction_risk_v1.md.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.fusion_result import FusionResult
from renaissance_v4.core.position_sizer import size_tier_to_fraction
from renaissance_v4.core.risk_decision import RiskDecision

# Effective-score tiers (post-compression). Calibrated from full-history directional bars
# (diagnostic_risk_v1.md): ~P50≈0.18, ~P75≈0.29, ~P90≈0.39, ~P95≈0.42 (histogram interpolation).
# Prior 0.55/0.70/0.90 vs ~0.19 avg effective made probe unreachable.
FULL_SIZE_FUSION_MIN = 0.42
REDUCED_SIZE_FUSION_MIN = 0.30
PROBE_SIZE_FUSION_MIN = 0.14

HIGH_VOLATILITY_VETO = 0.030
HIGH_VOLATILITY_REDUCE = 0.015

# Persistence: pre-v1.1, persistence<=0.25 hard-zeroed too many directional bars (see diagnostic_risk_v1).
LOW_PERSISTENCE_VETO = 0.08
LOW_PERSISTENCE_REDUCE = 0.40
PERSISTENCE_SOFT_MULTIPLIER = 0.72

DRAWDOWN_PLACEHOLDER_FULL = 0.00
DRAWDOWN_PLACEHOLDER_REDUCED = 0.10
DRAWDOWN_PLACEHOLDER_ZERO = 0.20


def evaluate_risk(
    fusion_result: FusionResult,
    features: FeatureSet,
    regime: str,
    drawdown_proxy: float = 0.0,
) -> RiskDecision:
    """
    Evaluate a fused decision and return an allowed/blocked size tier with explicit reasons.
    Phase 5 uses a drawdown proxy placeholder so later phases can wire in real account state.
    """
    veto_reasons: list[str] = []
    compression_factor = 1.0
    size_tier = "zero"
    allowed = False

    if fusion_result.direction == "no_trade":
        veto_reasons.append("no_trade_from_fusion")
        return RiskDecision(
            allowed=False,
            size_tier="zero",
            notional_fraction=0.0,
            compression_factor=0.0,
            veto_reasons=veto_reasons,
            debug_trace={
                "fusion_score": fusion_result.fusion_score,
                "regime": regime,
                "drawdown_proxy": drawdown_proxy,
            },
        )

    if fusion_result.conflict_score > 0.35:
        compression_factor *= 0.50
        veto_reasons.append("conflict_score_elevated")

    if fusion_result.overlap_penalty > 0.10:
        compression_factor *= 0.75
        veto_reasons.append("overlap_penalty_elevated")

    if regime == "unstable":
        compression_factor = 0.0
        veto_reasons.append("unstable_regime")
    elif regime == "volatility_expansion":
        compression_factor *= 0.75
        veto_reasons.append("volatility_expansion_compression")

    if features.volatility_20 >= HIGH_VOLATILITY_VETO:
        compression_factor = 0.0
        veto_reasons.append("volatility_too_high")
    elif features.volatility_20 >= HIGH_VOLATILITY_REDUCE:
        compression_factor *= 0.62
        veto_reasons.append("volatility_compression_applied")

    if features.directional_persistence_10 <= LOW_PERSISTENCE_VETO:
        compression_factor = 0.0
        veto_reasons.append("persistence_too_low")
    elif features.directional_persistence_10 <= LOW_PERSISTENCE_REDUCE:
        compression_factor *= PERSISTENCE_SOFT_MULTIPLIER
        veto_reasons.append("persistence_compression_applied")

    if drawdown_proxy >= DRAWDOWN_PLACEHOLDER_ZERO:
        compression_factor = 0.0
        veto_reasons.append("drawdown_proxy_block")
    elif drawdown_proxy >= DRAWDOWN_PLACEHOLDER_REDUCED:
        compression_factor *= 0.50
        veto_reasons.append("drawdown_proxy_reduction")

    effective_score = fusion_result.fusion_score * compression_factor

    if compression_factor <= 0.0:
        size_tier = "zero"
    elif effective_score >= FULL_SIZE_FUSION_MIN and drawdown_proxy <= DRAWDOWN_PLACEHOLDER_FULL:
        size_tier = "full"
    elif effective_score >= REDUCED_SIZE_FUSION_MIN:
        size_tier = "reduced"
    elif effective_score >= PROBE_SIZE_FUSION_MIN:
        size_tier = "probe"
    else:
        size_tier = "zero"
        veto_reasons.append("effective_score_below_probe_floor")

    notional_fraction = size_tier_to_fraction(size_tier)
    allowed = size_tier != "zero"

    decision = RiskDecision(
        allowed=allowed,
        size_tier=size_tier,
        notional_fraction=notional_fraction,
        compression_factor=compression_factor,
        veto_reasons=[] if allowed else veto_reasons,
        debug_trace={
            "fusion_direction": fusion_result.direction,
            "fusion_score": fusion_result.fusion_score,
            "effective_score": effective_score,
            "conflict_score": fusion_result.conflict_score,
            "overlap_penalty": fusion_result.overlap_penalty,
            "volatility_20": features.volatility_20,
            "directional_persistence_10": features.directional_persistence_10,
            "regime": regime,
            "drawdown_proxy": drawdown_proxy,
            "raw_veto_reasons": veto_reasons,
        },
    )

    print(
        "[risk_governor] Risk decision "
        f"allowed={decision.allowed} size_tier={decision.size_tier} "
        f"notional_fraction={decision.notional_fraction:.2f} "
        f"compression_factor={decision.compression_factor:.4f} "
        f"reasons={veto_reasons}"
    )

    return decision
