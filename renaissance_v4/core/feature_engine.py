"""
feature_engine.py

Purpose:
Convert MarketState into a deterministic FeatureSet for RenaissanceV4.

Usage:
Used by the replay runner after the MarketState builder.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.utils.math_utils import ema, safe_mean, safe_stddev

FAST_EMA_PERIOD = 10
SLOW_EMA_PERIOD = 20
VOL_WINDOW = 20
ATR_WINDOW = 14
PERSISTENCE_WINDOW = 10


def build_feature_set(state: MarketState) -> FeatureSet:
    """
    Build a deterministic FeatureSet from the current MarketState.
    Prints a compact feature summary for visible debugging.
    """
    candle_range = state.current_high - state.current_low
    candle_body = abs(state.current_close - state.current_open)
    upper_wick = state.current_high - max(state.current_open, state.current_close)
    lower_wick = min(state.current_open, state.current_close) - state.current_low

    one_bar_return = 0.0
    if len(state.closes) >= 2 and state.closes[-2] != 0:
        one_bar_return = (state.closes[-1] - state.closes[-2]) / state.closes[-2]

    avg_close_20 = safe_mean(state.closes[-20:])
    avg_volume_20 = safe_mean(state.volumes[-20:])

    ema_fast_10 = ema(state.closes[-FAST_EMA_PERIOD * 3 :], FAST_EMA_PERIOD)
    ema_slow_20 = ema(state.closes[-SLOW_EMA_PERIOD * 3 :], SLOW_EMA_PERIOD)
    ema_distance = ema_fast_10 - ema_slow_20

    prior_ema_fast = ema(state.closes[-(FAST_EMA_PERIOD * 3 + 1) : -1], FAST_EMA_PERIOD)
    ema_slope = ema_fast_10 - prior_ema_fast

    close_returns = []
    for index in range(1, len(state.closes[-VOL_WINDOW:])):
        previous_close = state.closes[-VOL_WINDOW:][index - 1]
        current_close = state.closes[-VOL_WINDOW:][index]
        if previous_close != 0:
            close_returns.append((current_close - previous_close) / previous_close)

    volatility_20 = safe_stddev(close_returns)

    recent_direction_flags = []
    close_slice = state.closes[-PERSISTENCE_WINDOW:]
    for index in range(1, len(close_slice)):
        if close_slice[index] > close_slice[index - 1]:
            recent_direction_flags.append(1.0)
        elif close_slice[index] < close_slice[index - 1]:
            recent_direction_flags.append(-1.0)
        else:
            recent_direction_flags.append(0.0)

    directional_persistence_10 = abs(safe_mean(recent_direction_flags))

    true_ranges = []
    lookback_highs = state.highs[-ATR_WINDOW:]
    lookback_lows = state.lows[-ATR_WINDOW:]
    lookback_closes = state.closes[-(ATR_WINDOW + 1) :]

    for index in range(len(lookback_highs)):
        high_value = lookback_highs[index]
        low_value = lookback_lows[index]
        previous_close = lookback_closes[index]
        true_range = max(
            high_value - low_value,
            abs(high_value - previous_close),
            abs(low_value - previous_close),
        )
        true_ranges.append(true_range)

    atr_proxy_14 = safe_mean(true_ranges)
    compression_ratio = 0.0
    if avg_close_20 != 0:
        compression_ratio = candle_range / avg_close_20

    feature_set = FeatureSet(
        close_price=state.current_close,
        candle_range=candle_range,
        candle_body=candle_body,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        one_bar_return=one_bar_return,
        avg_close_20=avg_close_20,
        avg_volume_20=avg_volume_20,
        ema_fast_10=ema_fast_10,
        ema_slow_20=ema_slow_20,
        ema_distance=ema_distance,
        ema_slope=ema_slope,
        volatility_20=volatility_20,
        directional_persistence_10=directional_persistence_10,
        atr_proxy_14=atr_proxy_14,
        compression_ratio=compression_ratio,
    )

    print(
        "[feature_engine] Features "
        f"close={feature_set.close_price:.4f} "
        f"ema_distance={feature_set.ema_distance:.4f} "
        f"ema_slope={feature_set.ema_slope:.4f} "
        f"volatility_20={feature_set.volatility_20:.6f} "
        f"persistence={feature_set.directional_persistence_10:.4f}"
    )

    return feature_set
