"""
trend_continuation.py

Purpose:
Implement the TrendContinuationSignal for RenaissanceV4.

Usage:
Used during replay to express directional continuation bias in strong trend conditions.

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

MIN_REGIME_FIT = 0.80
MIN_CONFIDENCE = 0.55


class TrendContinuationSignal(BaseSignal):
    """
    Express directional continuation when the trend regime is already established.
    """

    signal_name = "trend_continuation"

    def __init__(self) -> None:
        self._min_confidence: float | None = None
        self._min_regime_fit: float | None = None

    def configure_from_manifest(self, manifest: dict[str, Any]) -> None:
        if "trend_continuation_min_confidence" in manifest:
            self._min_confidence = float(manifest["trend_continuation_min_confidence"])
        if "trend_continuation_min_regime_fit" in manifest:
            self._min_regime_fit = float(manifest["trend_continuation_min_regime_fit"])

    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        direction = "neutral"
        confidence = 0.0
        expected_edge = 0.0
        regime_fit = 0.0
        stability_score = min(1.0, features.directional_persistence_10)
        active = False
        suppression_reason = ""

        if regime == "trend_up":
            regime_fit = 1.0
            if features.ema_distance > 0 and features.ema_slope > 0 and features.one_bar_return >= 0:
                direction = "long"
                confidence = min(1.0, 0.50 + abs(features.ema_slope) * 5 + features.directional_persistence_10 * 0.25)
                expected_edge = min(1.0, abs(features.ema_distance) / max(features.close_price, 1e-9))
        elif regime == "trend_down":
            regime_fit = 1.0
            if features.ema_distance < 0 and features.ema_slope < 0 and features.one_bar_return <= 0:
                direction = "short"
                confidence = min(1.0, 0.50 + abs(features.ema_slope) * 5 + features.directional_persistence_10 * 0.25)
                expected_edge = min(1.0, abs(features.ema_distance) / max(features.close_price, 1e-9))
        else:
            suppression_reason = f"regime_mismatch:{regime}"

        if direction == "neutral":
            if not suppression_reason:
                suppression_reason = "trend_conditions_not_met"
        else:
            need_r = self._min_regime_fit if self._min_regime_fit is not None else MIN_REGIME_FIT
            need_c = self._min_confidence if self._min_confidence is not None else MIN_CONFIDENCE
            active = regime_fit >= need_r and confidence >= need_c
            if not active:
                suppression_reason = "confidence_or_regime_fit_below_floor"

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
                "ema_slope": features.ema_slope,
                "one_bar_return": features.one_bar_return,
                "directional_persistence_10": features.directional_persistence_10,
            },
        )

        print(
            f"[signal:{self.signal_name}] direction={result.direction} "
            f"active={result.active} confidence={result.confidence:.4f} "
            f"reason={result.suppression_reason}"
        )

        return result
