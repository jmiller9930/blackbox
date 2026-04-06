"""Baseline signal — **Jupiter trade policy** (Sean’s rules): parity with ``trading_core`` signal math.

Entry rules mirror the SOL bot’s ``aggregateCandles`` + ``rsi`` logic (RSI swing + structure, same
constants). This module is **Jupiter trade policy** measurement only.

Catalog id ``jupiter_supertrend_ema_rsi_atr_v1``. Short precedence when both flags would fire.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# --- Parity: trading_core SOL bot constants (aggregateCandles / rsi) ---
RSI_PERIOD = 14
RSI_SHORT_THRESHOLD = 60
RSI_LONG_THRESHOLD = 40
PRICE_EPSILON = 0.001
RSI_EPSILON = 0.05
# Minimum candles: ``aggregateCandles`` requires ``df5min.length >= RSI_PERIOD + 2``
MIN_BARS = RSI_PERIOD + 2

REFERENCE_SOURCE = "trading_core:jupiter_policy:aggregateCandles+rsi"


@dataclass(frozen=True)
class SeanJupiterBaselineSignalV1:
    """Outcome of evaluating the **latest** closed bar vs the prior bar."""

    trade: bool
    side: str  # "long" | "short" | "flat"
    reason_code: str
    pnl_usd: float | None
    features: dict[str, Any]


def rsi_trading_core(series: list[float], period: int = RSI_PERIOD) -> list[float]:
    """
    Port of ``trading_core`` ``rsi`` (same smoothing). ``rsiValues[i]`` is NaN until ``i >= period``.
    """
    n = len(series)
    rsi_values = [float("nan")] * n
    if n < period:
        return rsi_values

    gain = 0.0
    loss = 0.0
    for i in range(1, period + 1):
        delta = series[i] - series[i - 1]
        if delta > 0:
            gain += delta
        else:
            loss -= delta

    avg_gain = gain / period
    avg_loss = loss / period
    if avg_gain == 0 and avg_loss == 0:
        avg_gain = 0.001
        avg_loss = 0.001

    if avg_loss == 0:
        rs = float("inf")
    else:
        rs = avg_gain / avg_loss
    rsi_values[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        delta = series[i] - series[i - 1]
        current_gain = delta if delta > 0 else 0.0
        current_loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + current_gain) / period
        avg_loss = (avg_loss * (period - 1) + current_loss) / period
        if avg_loss == 0:
            rs = float("inf")
        else:
            rs = avg_gain / avg_loss
        rsi_values[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi_values


def aggregate_candles_signal_flags(
    *,
    prev_candle: dict[str, float],
    curr_candle: dict[str, float],
    prev_rsi_raw: float,
    current_rsi_raw: float,
) -> tuple[bool, bool]:
    """
    Exact boolean logic from ``aggregateCandles`` (lines 797–798).

    ``prev_candle`` / ``curr_candle`` use keys: high, low (floats).
    """
    ph = prev_candle["high"]
    pl = prev_candle["low"]
    ch = curr_candle["high"]
    cl = curr_candle["low"]

    short_signal = (
        (ch - ph > PRICE_EPSILON)
        and (prev_rsi_raw - current_rsi_raw > RSI_EPSILON)
        and (current_rsi_raw > RSI_SHORT_THRESHOLD)
    )
    long_signal = (
        (pl - cl > PRICE_EPSILON)
        and (current_rsi_raw - prev_rsi_raw > RSI_EPSILON)
        and (current_rsi_raw < RSI_LONG_THRESHOLD)
    )
    return short_signal, long_signal


def evaluate_sean_jupiter_baseline_v1(
    *,
    bars_asc: list[dict[str, Any]],
) -> SeanJupiterBaselineSignalV1:
    """
    Evaluate **latest** bar (``bars_asc[-1]``) as ``currCandle`` and ``bars_asc[-2]`` as ``prevCandle``.

    Same indexing as ``trading_core``: ``i = len - 1``, RSI at ``i`` and ``i-1`` over **all** closes in
    ``bars_asc``.
    """
    if len(bars_asc) < MIN_BARS:
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="insufficient_history",
            pnl_usd=None,
            features={
                "bars_asc_len": len(bars_asc),
                "min_bars": MIN_BARS,
                "reference": REFERENCE_SOURCE,
            },
        )

    prev_bar = bars_asc[-2]
    cur = bars_asc[-1]
    try:
        prev_candle = {
            "high": float(prev_bar["high"]),
            "low": float(prev_bar["low"]),
        }
        curr_candle = {
            "high": float(cur["high"]),
            "low": float(cur["low"]),
        }
        o = float(cur["open"])
        c = float(cur["close"])
        closes = [float(b["close"]) for b in bars_asc]
    except (TypeError, ValueError, KeyError):
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="ohlc_parse_error",
            pnl_usd=None,
            features={"reference": REFERENCE_SOURCE},
        )

    rsi_values = rsi_trading_core(closes, RSI_PERIOD)
    i = len(bars_asc) - 1
    prev_rsi_raw = rsi_values[i - 1]
    current_rsi_raw = rsi_values[i]

    if math.isnan(prev_rsi_raw) or math.isnan(current_rsi_raw):
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="rsi_nan",
            pnl_usd=None,
            features={"reference": REFERENCE_SOURCE},
        )

    short_signal, long_signal = aggregate_candles_signal_flags(
        prev_candle=prev_candle,
        curr_candle=curr_candle,
        prev_rsi_raw=prev_rsi_raw,
        current_rsi_raw=current_rsi_raw,
    )

    feat = {
        "reference": REFERENCE_SOURCE,
        "catalog_id": "jupiter_supertrend_ema_rsi_atr_v1",
        "parity": "jupiter_policy_aggregateCandles_rsi",
        "prev_rsi": round(prev_rsi_raw, 8),
        "current_rsi": round(current_rsi_raw, 8),
        "short_signal": short_signal,
        "long_signal": long_signal,
    }

    if not short_signal and not long_signal:
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="no_signal",
            pnl_usd=None,
            features=feat,
        )

    # ``processSignals(shortSignal, longSignal)`` uses short first (line 1016).
    if short_signal:
        side = "short"
        pnl = (o - c) * 1.0
        reason = "jupiter_policy_short_signal"
    else:
        side = "long"
        pnl = (c - o) * 1.0
        reason = "jupiter_policy_long_signal"

    return SeanJupiterBaselineSignalV1(
        trade=True,
        side=side,
        reason_code=reason,
        pnl_usd=round(pnl, 8),
        features=feat,
    )
