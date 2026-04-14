"""
mean_reversion_fade.py

Purpose:
Implement the MeanReversionFadeSignal for RenaissanceV4.

Usage:
Used during replay to express fade bias when price appears stretched in non-trending conditions.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.signals.base_signal import BaseSignal
from renaissance_v4.signals.signal_result import SignalResult

MIN_CONFIDENCE = 0.53


class MeanReversionFadeSignal(BaseSignal):
    """
    Express reversal bias away from local stretch in range or compressed environments.
    """

    signal_name = "mean_reversion_fade"

    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        direction = "neutral"
        confidence = 0.0
        expected_edge = 0.0
        regime_fit = 0.0
        stability_score = 0.65
        active = False
        suppression_reason = ""

        deviation_from_mean = 0.0
        if features.avg_close_20 != 0:
            deviation_from_mean = (features.close_price - features.avg_close_20) / features.avg_close_20

        range_like_regime = regime in {"range", "volatility_compression"}

        if range_like_regime:
            regime_fit = 0.90
            if deviation_from_mean > 0.003 and features.one_bar_return >= 0:
                direction = "short"
                confidence = min(1.0, 0.45 + abs(deviation_from_mean) * 40)
                expected_edge = min(1.0, abs(deviation_from_mean) * 10)
            elif deviation_from_mean < -0.003 and features.one_bar_return <= 0:
                direction = "long"
                confidence = min(1.0, 0.45 + abs(deviation_from_mean) * 40)
                expected_edge = min(1.0, abs(deviation_from_mean) * 10)
            else:
                suppression_reason = "stretch_threshold_not_met"
        else:
            suppression_reason = f"regime_mismatch:{regime}"

        if direction != "neutral":
            active = confidence >= MIN_CONFIDENCE
            if not active:
                suppression_reason = "confidence_below_floor"

        result = SignalResult(
            signal_name=self.signal_name,
            direction=direction,
            confidence=confidence,
            expected_edge=expected_edge,
            regime_fit=regime_fit,
            stability_score=stability_score,
            active=active,
            suppression_reason=suppression_reason if not active else "",
            evidence_trace={
                "regime": regime,
                "close_price": features.close_price,
                "avg_close_20": features.avg_close_20,
                "deviation_from_mean": deviation_from_mean,
                "one_bar_return": features.one_bar_return,
            },
        )

        print(
            f"[signal:{self.signal_name}] direction={result.direction} "
            f"active={result.active} confidence={result.confidence:.4f} "
            f"reason={result.suppression_reason}"
        )

        return result
