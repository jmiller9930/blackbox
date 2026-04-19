"""
breakout_expansion.py

Purpose:
Implement the BreakoutExpansionSignal for RenaissanceV4.

Usage:
Used during replay to detect expansion after relatively compressed conditions.

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

MIN_CONFIDENCE = 0.56


class BreakoutExpansionSignal(BaseSignal):
    """
    Express breakout bias after compression begins to release.
    """

    signal_name = "breakout_expansion"

    def __init__(self) -> None:
        self._min_confidence: float | None = None

    def configure_from_manifest(self, manifest: dict[str, Any]) -> None:
        if "breakout_expansion_min_confidence" in manifest:
            self._min_confidence = float(manifest["breakout_expansion_min_confidence"])

    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        direction = "neutral"
        confidence = 0.0
        expected_edge = 0.0
        regime_fit = 0.0
        stability_score = 0.70
        active = False
        suppression_reason = ""

        avg_close = max(features.avg_close_20, 1e-9)
        large_bar = features.candle_range / avg_close > 0.004

        if regime == "volatility_expansion":
            regime_fit = 1.0
            if features.one_bar_return > 0 and large_bar and features.ema_slope >= 0:
                direction = "long"
                confidence = min(1.0, 0.50 + features.volatility_20 * 10 + features.compression_ratio * 20)
                expected_edge = min(1.0, features.candle_range / avg_close)
            elif features.one_bar_return < 0 and large_bar and features.ema_slope <= 0:
                direction = "short"
                confidence = min(1.0, 0.50 + features.volatility_20 * 10 + features.compression_ratio * 20)
                expected_edge = min(1.0, features.candle_range / avg_close)
            else:
                suppression_reason = "expansion_detected_but_direction_unclear"
        else:
            suppression_reason = f"regime_mismatch:{regime}"

        if direction != "neutral":
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
                "one_bar_return": features.one_bar_return,
                "candle_range": features.candle_range,
                "avg_close_20": features.avg_close_20,
                "volatility_20": features.volatility_20,
                "compression_ratio": features.compression_ratio,
                "ema_slope": features.ema_slope,
            },
        )

        print(
            f"[signal:{self.signal_name}] direction={result.direction} "
            f"active={result.active} confidence={result.confidence:.4f} "
            f"reason={result.suppression_reason}"
        )

        return result
