"""
feature_set.py

Purpose:
Define the canonical FeatureSet object for one replay step.

Usage:
Produced by the feature engine and consumed by the regime classifier and future signals.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FeatureSet:
    """
    Holds deterministic features derived from the current MarketState.
    """

    close_price: float
    candle_range: float
    candle_body: float
    upper_wick: float
    lower_wick: float
    one_bar_return: float
    avg_close_20: float
    avg_volume_20: float
    ema_fast_10: float
    ema_slow_20: float
    ema_distance: float
    ema_slope: float
    volatility_20: float
    directional_persistence_10: float
    atr_proxy_14: float
    compression_ratio: float
