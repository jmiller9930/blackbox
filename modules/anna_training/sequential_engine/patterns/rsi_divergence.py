"""Deterministic RSI + swing divergence (explicit rules)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _rsi_wilder(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder RSI via pandas ewm (alpha = 1/period), deterministic."""
    c = np.asarray(close, dtype=float).ravel()
    if c.size < period + 1:
        raise ValueError("close too short for RSI")
    s = pd.Series(c)
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / float(period), adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / float(period), adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.to_numpy(dtype=float)


def _swing_highs_lows(close: np.ndarray, swing: int) -> tuple[list[int], list[int]]:
    """Indices of local maxima / minima with ``swing`` bars on each side."""
    c = np.asarray(close, dtype=float).ravel()
    highs: list[int] = []
    lows: list[int] = []
    for i in range(swing, len(c) - swing):
        w = c[i - swing : i + swing + 1]
        if c[i] == np.max(w):
            highs.append(i)
        if c[i] == np.min(w):
            lows.append(i)
    return highs, lows


def run_rsi_divergence_scan(
    close: np.ndarray,
    *,
    rsi_period: int = 14,
    swing: int = 2,
) -> dict[str, Any]:
    """
    Bearish divergence: price higher high, RSI lower high (last two swing highs).
    Bullish divergence: price lower low, RSI higher low (last two swing lows).
    """
    c = np.asarray(close, dtype=float).ravel()
    rsi = _rsi_wilder(c, rsi_period)
    highs, lows = _swing_highs_lows(c, swing)

    bearish = False
    bullish = False
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        if c[i2] > c[i1] and rsi[i2] < rsi[i1]:
            bearish = True
    if len(lows) >= 2:
        j1, j2 = lows[-2], lows[-1]
        if c[j2] < c[j1] and rsi[j2] > rsi[j1]:
            bullish = True

    return {
        "method": "rsi_divergence_deterministic",
        "rsi_period": int(rsi_period),
        "swing": int(swing),
        "n": int(c.size),
        "bearish_divergence": bearish,
        "bullish_divergence": bullish,
        "pattern_spec_hash_inputs": {
            "method": "rsi_divergence_deterministic",
            "rsi_period": int(rsi_period),
            "swing": int(swing),
        },
    }
