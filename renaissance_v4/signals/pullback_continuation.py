"""
pullback_continuation.py

Purpose:
Implement the PullbackContinuationSignal for RenaissanceV4.

Usage:
Used during replay to detect controlled retracement opportunities inside an active trend.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from typing import Any

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.signals.base_signal import BaseSignal
from renaissance_v4.signals.signal_result import SignalResult

MIN_CONFIDENCE = 0.52
DEFAULT_VOLATILITY_CEILING = 0.02


class PullbackContinuationSignal(BaseSignal):
    """
    Express continuation after a controlled pullback inside a prevailing trend.
    """

    signal_name = "pullback_continuation"

    def __init__(self) -> None:
        self._min_confidence: float | None = None
        self._volatility_ceiling: float | None = None

    def configure_from_manifest(self, manifest: dict[str, Any]) -> None:
        if "pullback_continuation_min_confidence" in manifest:
            self._min_confidence = float(manifest["pullback_continuation_min_confidence"])
        if "pullback_continuation_volatility_threshold" in manifest:
            self._volatility_ceiling = float(manifest["pullback_continuation_volatility_threshold"])

    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        direction = "neutral"
        confidence = 0.0
        expected_edge = 0.0
        regime_fit = 0.0
        stability_score = min(1.0, 0.5 + features.directional_persistence_10 * 0.5)
        active = False
        suppression_reason = ""

        pulled_back = features.candle_body < max(features.candle_range * 0.60, 1e-9)
        vol_cap = (
            self._volatility_ceiling
            if self._volatility_ceiling is not None
            else DEFAULT_VOLATILITY_CEILING
        )
        not_explosive = features.volatility_20 < vol_cap

        if regime == "trend_up":
            regime_fit = 0.90
            if features.ema_distance > 0 and features.one_bar_return <= 0 and pulled_back and not_explosive:
                direction = "long"
                confidence = min(1.0, 0.45 + features.directional_persistence_10 * 0.20 + abs(features.ema_distance) / max(features.close_price, 1e-9))
                expected_edge = min(1.0, abs(features.ema_distance) / max(features.close_price, 1e-9))
        elif regime == "trend_down":
            regime_fit = 0.90
            if features.ema_distance < 0 and features.one_bar_return >= 0 and pulled_back and not_explosive:
                direction = "short"
                confidence = min(1.0, 0.45 + features.directional_persistence_10 * 0.20 + abs(features.ema_distance) / max(features.close_price, 1e-9))
                expected_edge = min(1.0, abs(features.ema_distance) / max(features.close_price, 1e-9))
        else:
            suppression_reason = f"regime_mismatch:{regime}"

        if direction == "neutral":
            if not suppression_reason:
                suppression_reason = "pullback_conditions_not_met"
        else:
            floor = self._min_confidence if self._min_confidence is not None else MIN_CONFIDENCE
            active = confidence >= floor
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
                "ema_distance": features.ema_distance,
                "one_bar_return": features.one_bar_return,
                "candle_body": features.candle_body,
                "candle_range": features.candle_range,
                "volatility_20": features.volatility_20,
            },
        )

        print(
            f"[signal:{self.signal_name}] direction={result.direction} "
            f"active={result.active} confidence={result.confidence:.4f} "
            f"reason={result.suppression_reason}"
        )

        return result
