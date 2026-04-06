"""Baseline signal — **Jupiter trade policy** (Sean’s rules, v2).

Combines:

- **aggregateCandles-style** structure + RSI swing (same boolean shape as the live bot’s
  ``aggregateCandles`` block: high/low deltas + RSI delta vs ``RSI_EPSILON``).
- **Sean Jupiter constants** (RSI 52/48, ATR 14, Supertrend ×3, EMA 200, min-notional hint).
- **Supertrend** (Wilder ATR, final upper/lower bands — TradingView-style step).
- **EMA200** filter: long only if ``close > EMA200``; short only if ``close < EMA200``.

Short precedence when both raw arms would fire. Catalog id ``jupiter_supertrend_ema_rsi_atr_v1``.

This is **paper measurement** only (no venue submit).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

# --- Sean Jupiter Perps policy (v2) — align with operator Jupiter bot constants ---
RSI_PERIOD = 14
RSI_SHORT_THRESHOLD = 48
RSI_LONG_THRESHOLD = 52
PRICE_EPSILON = 0.001
RSI_EPSILON = 0.05

ATR_PERIOD = 14
SUPERTREND_MULTIPLIER = 3.0
EMA_PERIOD = 200
MIN_NOTIONAL_USD = 10

# Need full EMA200 + RSI at last index; 200 bars covers EMA200 at the last close.
MIN_BARS = EMA_PERIOD

REFERENCE_SOURCE = "jupiter_sean_policy:v2:aggregateCandles+rsi+supertrend+ema200"


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


def wilder_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = ATR_PERIOD,
) -> list[float]:
    """Wilder ATR; value at index ``period`` is first defined (NaN before)."""
    n = len(closes)
    atr = [float("nan")] * n
    if n < period + 1:
        return atr
    tr = [0.0] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    atr[period] = sum(tr[1 : period + 1]) / period
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def supertrend_direction_series(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    atr_period: int = ATR_PERIOD,
    multiplier: float = SUPERTREND_MULTIPLIER,
) -> list[int]:
    """
    TradingView-style Supertrend **direction**: ``1`` bullish, ``-1`` bearish, ``0`` unknown.

    Uses hl2 ± multiplier * ATR for basic bands; final bands follow Pine-style hold rules.
    """
    n = len(closes)
    out = [0] * n
    if n < atr_period + 2:
        return out
    atr = wilder_atr(highs, lows, closes, atr_period)
    src = [(highs[i] + lows[i]) / 2 for i in range(n)]
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(n):
        if math.isnan(atr[i]):
            continue
        ub = src[i] + multiplier * atr[i]
        lb = src[i] - multiplier * atr[i]
        if i == 0 or upper[i - 1] is None:
            upper[i] = ub
            lower[i] = lb
            continue
        pu = float(upper[i - 1])
        pl = float(lower[i - 1])
        pc = closes[i - 1]
        lower[i] = lb if (lb > pl or pc < pl) else pl
        upper[i] = ub if (ub < pu or pc > pu) else pu

    for i in range(1, n):
        if upper[i - 1] is None or lower[i - 1] is None or upper[i] is None or lower[i] is None:
            continue
        pu = float(upper[i - 1])
        pl = float(lower[i - 1])
        c = closes[i]
        if c > pu:
            out[i] = 1
        elif c < pl:
            out[i] = -1
        else:
            out[i] = out[i - 1]
    return out


def aggregate_candles_signal_flags(
    *,
    prev_candle: dict[str, float],
    curr_candle: dict[str, float],
    prev_rsi_raw: float,
    current_rsi_raw: float,
) -> tuple[bool, bool]:
    """
    Same boolean **shape** as ``aggregateCandles`` (high/low structure + RSI swing + thresholds).

    Thresholds are **Sean's Jupiter v2** (52 / 48), not the deprecated Drift snapshot (40 / 60).
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

    RSI indexing matches ``trading_core``: ``i = len - 1``, RSI at ``i`` and ``i-1`` over **all** closes.
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
        highs = [float(b["high"]) for b in bars_asc]
        lows = [float(b["low"]) for b in bars_asc]
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

    st_dir = supertrend_direction_series(highs, lows, closes)[i]
    ema200_s = pd.Series(closes, dtype=float).ewm(span=EMA_PERIOD, adjust=False).mean()
    ema200_last = float(ema200_s.iloc[-1])

    raw_short = short_signal
    raw_long = long_signal
    short_ok = raw_short and st_dir == -1 and c < ema200_last
    long_ok = raw_long and st_dir == 1 and c > ema200_last

    feat: dict[str, Any] = {
        "reference": REFERENCE_SOURCE,
        "catalog_id": "jupiter_supertrend_ema_rsi_atr_v1",
        "parity": "jupiter_policy_v2:aggregateCandles_rsi+supertrend+ema200",
        "policy_version": "sean_jupiter_v2",
        "prev_rsi": round(prev_rsi_raw, 8),
        "current_rsi": round(current_rsi_raw, 8),
        "short_signal_raw": raw_short,
        "long_signal_raw": raw_long,
        "short_signal": short_ok,
        "long_signal": long_ok,
        "supertrend_direction": st_dir,
        "ema200": round(ema200_last, 8),
        "close": round(c, 8),
        "min_notional_hint_usd": MIN_NOTIONAL_USD,
    }

    if not raw_short and not raw_long:
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="no_signal",
            pnl_usd=None,
            features=feat,
        )

    blockers: list[str] = []
    if raw_short and not short_ok:
        if st_dir != -1:
            blockers.append("supertrend_not_bearish")
        elif c >= ema200_last:
            blockers.append("ema200_blocks_short")
    if raw_long and not long_ok:
        if st_dir != 1:
            blockers.append("supertrend_not_bullish")
        elif c <= ema200_last:
            blockers.append("ema200_blocks_long")

    if not short_ok and not long_ok:
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="policy_filter_block",
            pnl_usd=None,
            features={**feat, "policy_blockers": blockers},
        )

    if short_ok:
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
