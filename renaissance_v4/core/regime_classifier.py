"""
regime_classifier.py

Purpose:
Classify the current market regime from deterministic Phase 2 features.

Usage:
Used by the replay runner after feature generation.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet

TREND_DISTANCE_THRESHOLD = 0.15
TREND_SLOPE_THRESHOLD = 0.02
PERSISTENCE_THRESHOLD = 0.60
VOLATILITY_EXPANSION_THRESHOLD = 0.008
VOLATILITY_COMPRESSION_THRESHOLD = 0.0025
COMPRESSION_RATIO_LOW = 0.0015
COMPRESSION_RATIO_HIGH = 0.008


def classify_regime(features: FeatureSet) -> str:
    """
    Classify the current market state into one of the Phase 2 regime buckets.
    Prints the chosen regime for visible debugging.
    """
    regime = "unstable"

    if (
        features.ema_distance > TREND_DISTANCE_THRESHOLD
        and features.ema_slope > TREND_SLOPE_THRESHOLD
        and features.directional_persistence_10 >= PERSISTENCE_THRESHOLD
    ):
        regime = "trend_up"
    elif (
        features.ema_distance < -TREND_DISTANCE_THRESHOLD
        and features.ema_slope < -TREND_SLOPE_THRESHOLD
        and features.directional_persistence_10 >= PERSISTENCE_THRESHOLD
    ):
        regime = "trend_down"
    elif (
        features.volatility_20 >= VOLATILITY_EXPANSION_THRESHOLD
        and features.compression_ratio >= COMPRESSION_RATIO_HIGH
    ):
        regime = "volatility_expansion"
    elif (
        features.volatility_20 <= VOLATILITY_COMPRESSION_THRESHOLD
        and features.compression_ratio <= COMPRESSION_RATIO_LOW
    ):
        regime = "volatility_compression"
    elif abs(features.ema_distance) < TREND_DISTANCE_THRESHOLD and features.directional_persistence_10 < PERSISTENCE_THRESHOLD:
        regime = "range"

    print(f"[regime_classifier] Regime classified as: {regime}")
    return regime
