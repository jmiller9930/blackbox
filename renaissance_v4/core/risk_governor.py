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
- v1.2 DV-ARCH-CORRECTION-013: unstable = probe-only path (compression + tier cap); higher full tier floor;
  weak-signal-only containment; mild range compression when persistence elevated.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.fusion_result import FusionResult
from renaissance_v4.core.position_sizer import size_tier_to_fraction
from renaissance_v4.core.risk_decision import RiskDecision

# Effective-score tiers (post-compression). Calibrated from full-history directional bars
# (diagnostic_risk_v1.md): ~P50≈0.18, ~P75≈0.29, ~P90≈0.39, ~P95≈0.42 (histogram interpolation).
# Prior 0.55/0.70/0.90 vs ~0.19 avg effective made probe unreachable.
# DV-013: full tier was worst in diagnostic_quality_v1 — raise bar so full is rare / high conviction.
FULL_SIZE_FUSION_MIN = 0.52
REDUCED_SIZE_FUSION_MIN = 0.30
PROBE_SIZE_FUSION_MIN = 0.14

WEAK_SIGNAL_FAMILY = frozenset({"trend_continuation", "pullback_continuation"})

HIGH_VOLATILITY_VETO = 0.030
HIGH_VOLATILITY_REDUCE = 0.015

# Persistence: pre-v1.1, persistence<=0.25 hard-zeroed too many directional bars (see diagnostic_risk_v1).
LOW_PERSISTENCE_VETO = 0.08
LOW_PERSISTENCE_REDUCE = 0.40
PERSISTENCE_SOFT_MULTIPLIER = 0.72

DRAWDOWN_PLACEHOLDER_FULL = 0.00
DRAWDOWN_PLACEHOLDER_REDUCED = 0.10
DRAWDOWN_PLACEHOLDER_ZERO = 0.20


def _active_signals_weak_only(active_signal_names: list[str] | None) -> bool:
    """True when every active signal is trend/pullback (diagnostic: sparse but very negative per trade)."""
    if not active_signal_names:
        return False
    return all(name in WEAK_SIGNAL_FAMILY for name in active_signal_names)


def evaluate_risk(
    fusion_result: FusionResult,
    features: FeatureSet,
    regime: str,
    drawdown_proxy: float = 0.0,
    active_signal_names: list[str] | None = None,
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

    # DV-013 option: restrict unstable to probe-only — do not hard-zero (that only affects entry; exit-time
    # "unstable" labels still dominate diagnostics). Use severe compression + hard cap at probe tier.
    unstable_probe_only = False
    if regime == "unstable":
        unstable_probe_only = True
        compression_factor *= 0.48
        veto_reasons.append("unstable_regime_severe_compression_probe_path")
    elif regime == "volatility_expansion":
        compression_factor *= 0.75
        veto_reasons.append("volatility_expansion_compression")

    if features.volatility_20 >= HIGH_VOLATILITY_VETO:
        compression_factor = 0.0
        veto_reasons.append("volatility_too_high")
    elif features.volatility_20 >= HIGH_VOLATILITY_REDUCE:
        compression_factor *= 0.62
        veto_reasons.append("volatility_compression_applied")

    if regime == "range" and features.directional_persistence_10 >= 0.50:
        compression_factor *= 0.90
        veto_reasons.append("range_elevated_persistence_compression")

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

    tier_adjustments: list[str] = []
    if unstable_probe_only and size_tier in ("reduced", "full"):
        size_tier = "probe"
        tier_adjustments.append("unstable_regime_tier_capped_probe")
    if _active_signals_weak_only(active_signal_names) and size_tier in ("reduced", "full"):
        size_tier = "probe"
        tier_adjustments.append("weak_signal_family_probe_cap")

    veto_reasons.extend(tier_adjustments)

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
            "active_signal_names": list(active_signal_names or []),
            "tier_adjustments": tier_adjustments,
            "unstable_probe_only": unstable_probe_only,
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
