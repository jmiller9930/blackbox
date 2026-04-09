"""Baseline signal — **Jupiter trade policy** (Sean’s rules, v2).

Combines:

- **aggregateCandles-style** structure + RSI swing (same boolean shape as the live bot’s
  ``aggregateCandles`` block: high/low deltas + RSI delta vs ``RSI_EPSILON``).
- **Sean Jupiter constants** (RSI 52/48, ATR 14, Supertrend ×3, EMA 200, min-notional hint).
- **Supertrend** (Wilder ATR, final upper/lower bands — TradingView-style step).
- **ATR ratio (tile + final veto)** — same as ``jupiter_2_sean_policy``: simple mean TR over 14 bars vs
  reference window (``calculate_atr`` / ``closes[-214:-14]``); not the Wilder-smoothed series.
- **EMA200** filter: long only if ``close > EMA200``; short only if ``close < EMA200``.

Short precedence when both raw arms would fire. Catalog id ``jupiter_supertrend_ema_rsi_atr_v1``.

This is **paper measurement** only (no venue submit).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from modules.anna_training.jupiter_2_sean_policy import calculate_atr

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

# Final veto on trade=True: current ATR vs trailing average of ATR (same series as tile).
ATR_RATIO_MIN = 1.35

# Need full EMA200 + RSI at last index; 200 bars covers EMA200 at the last close.
MIN_BARS = EMA_PERIOD

REFERENCE_SOURCE = "jupiter_sean_policy:v2:aggregateCandles+rsi+supertrend+ema200"


def _resolve_atr_ratio_from_features(feat: dict[str, Any]) -> float | None:
    """
    ``tile`` from :func:`_build_tile_payload` carries ``atr_ratio`` and/or ``atr_current`` / ``atr_avg200``.

    Ratio matches :func:`modules.anna_training.jupiter_2_sean_policy.generate_signal_from_ohlc`
    (simple mean TR / reference window — not Wilder-smoothed ATR series).
    Used only as the final trade veto (not for raw/ST/EMA gates).
    """
    tile = feat.get("tile")
    if not isinstance(tile, dict):
        return None
    r = tile.get("atr_ratio")
    if r is not None:
        try:
            rf = float(r)
            if not math.isnan(rf):
                return rf
        except (TypeError, ValueError):
            pass
    ac = tile.get("atr_current")
    aa = tile.get("atr_avg200")
    if ac is None or aa is None:
        return None
    try:
        a = float(ac)
        b = float(aa)
    except (TypeError, ValueError):
        return None
    if math.isnan(a) or math.isnan(b) or b <= 0:
        return None
    return a / b


def _volume_from_bar(bar: dict[str, Any]) -> float | int | None:
    v = bar.get("volume_base")
    if v is not None:
        try:
            return float(v)
        except (TypeError, ValueError):
            pass
    t = bar.get("tick_count")
    if t is not None:
        try:
            return int(t)
        except (TypeError, ValueError):
            pass
    return None


def _build_tile_payload(
    *,
    bars_asc: list[dict[str, Any]],
    prev_bar: dict[str, Any],
    cur: dict[str, Any],
    i: int,
    prev_rsi_raw: float,
    current_rsi_raw: float,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    st_dir: int,
    ema200_last: float,
    raw_short: bool,
    raw_long: bool,
    short_ok: bool,
    long_ok: bool,
) -> dict[str, Any]:
    """Rich context for operator tiles (same bar math as policy)."""
    # ATR ratio — align with jupiter_2_sean_policy / TypeScript: simple mean TR (not Wilder).
    # Wilder ATR remains used for Supertrend bands (above) only.
    atr_simple = calculate_atr(closes, highs, lows)
    if len(closes) >= 214:
        avg_atr = calculate_atr(
            closes[-214:-14],
            highs[-214:-14],
            lows[-214:-14],
        )
    elif len(closes) >= 200:
        # Jupiter uses len>=200 with a 200-bar slice; that slice is empty until len>=214.
        avg_atr = atr_simple
    else:
        avg_atr = atr_simple
    ratio = (
        (float(atr_simple) / float(avg_atr))
        if avg_atr and avg_atr > 0
        else 1.0
    )

    po = float(prev_bar["open"])
    ph = float(prev_bar["high"])
    pl = float(prev_bar["low"])
    pc = float(prev_bar["close"])
    co = float(cur["open"])
    ch = float(cur["high"])
    cl = float(cur["low"])
    cc = float(cur["close"])
    higher_close = cc > pc
    lower_close = cc < pc

    vol = _volume_from_bar(cur)
    ts = str(cur.get("candle_open_utc") or cur.get("candle_close_utc") or "").strip()

    if st_dir == 1:
        st_label = "BULLISH (green)"
    elif st_dir == -1:
        st_label = "BEARISH (red)"
    else:
        st_label = "NEUTRAL"

    if cc > ema200_last:
        pvsem = "ABOVE"
    elif cc < ema200_last:
        pvsem = "BELOW"
    else:
        pvsem = "AT"

    rsi_above_52 = current_rsi_raw > float(RSI_LONG_THRESHOLD)
    rsi_below_48 = current_rsi_raw < float(RSI_SHORT_THRESHOLD)

    return {
        "tile": {
            "candle_open_utc": ts,
            "new_ohlcv": {"o": co, "h": ch, "l": cl, "c": cc, "v": vol},
            "prev_ohlc": {"o": po, "h": ph, "l": pl, "c": pc},
            "prev_rsi": prev_rsi_raw,
            "current_rsi": current_rsi_raw,
            "supertrend_label": st_label,
            "supertrend_direction": st_dir,
            "atr_current": float(atr_simple),
            "atr_avg200": float(avg_atr) if avg_atr and avg_atr > 0 else None,
            "atr_ratio": float(ratio),
            "price_vs_ema200": pvsem,
            "ema200": float(ema200_last),
            "higher_close": higher_close,
            "lower_close": lower_close,
            "breakdown_long": {
                "supertrend_bullish": st_dir == 1,
                "above_ema": cc > ema200_last,
                "rsi_long_arm_raw": raw_long,
                "rsi_gt_52": rsi_above_52,
                "higher_close": higher_close,
                "long_ok": long_ok,
            },
            "breakdown_short": {
                "supertrend_bearish": st_dir == -1,
                "below_ema": cc < ema200_last,
                "rsi_short_arm_raw": raw_short,
                "rsi_lt_48": rsi_below_48,
                "lower_close": lower_close,
                "short_ok": short_ok,
            },
            "bars_asc_len": len(bars_asc),
        }
    }


def _tile_ts_iso_z(ts: str) -> str:
    """Normalize to ``...T..:..:..(.fff)?Z`` (add ``.000`` before Z when seconds have no fraction)."""
    s = (ts or "").strip()
    if not s:
        return s
    if s.endswith("Z") and "." not in s[10:]:
        # e.g. 2026-04-06T18:30:00Z → 2026-04-06T18:30:00.000Z
        if len(s) >= 20 and s[-1] == "Z":
            return s[:-1] + ".000Z"
    return s


def _tile_fmt_price(v: Any) -> str:
    """Stable decimal text for OHLC/ATR/EMA (avoid float print artifacts)."""
    if v is None:
        return ""
    try:
        f = float(v)
        r = round(f, 12)
        t = f"{r:.12f}".rstrip("0").rstrip(".")
        return t if t else "0"
    except (TypeError, ValueError):
        return str(v)


def _tile_fmt_rsi(v: Any) -> str:
    if v is None:
        return ""
    try:
        f = float(v)
        r = round(f, 12)
        t = f"{r:.15f}".rstrip("0").rstrip(".")
        return t if t else "0"
    except (TypeError, ValueError):
        return str(v)


def _tile_lower_bool(x: Any) -> str:
    if x is True:
        return "true"
    if x is False:
        return "false"
    return str(x).lower()


def format_jupiter_tile_narrative_v1(
    *,
    features: dict[str, Any],
    reason_code: str,
    trade: bool,
    side: str,
    policy_blockers: list[str] | None = None,
) -> str:
    """
    Human-readable multi-line tile — **operator contract** (fixed line shapes, labels, order).

    Uses ``features["tile"]`` when present (populated by :func:`evaluate_sean_jupiter_baseline_v1`).
    """
    lines: list[str] = []
    tile = features.get("tile") if isinstance(features.get("tile"), dict) else {}
    if not tile:
        return (
            f"Policy: {REFERENCE_SOURCE}\n"
            f"reason_code={reason_code}\n"
            f"trade={trade} side={side}\n"
            "(Insufficient bar context for full OHLC/ATR tile — need closed bar history.)"
        )

    ts = _tile_ts_iso_z(str(tile.get("candle_open_utc") or ""))
    nv = tile.get("new_ohlcv") or {}
    vo, vh, vl, vc = nv.get("o"), nv.get("h"), nv.get("l"), nv.get("c")
    vv = nv.get("v")
    vol_s = ""
    if vv is not None:
        try:
            fv = float(vv)
            vol_s = str(int(fv)) if fv.is_integer() else _tile_fmt_price(fv)
        except (TypeError, ValueError):
            vol_s = str(vv)

    lines.append(
        "New 5-min candle formed: Timestamp="
        + ts
        + ", O="
        + _tile_fmt_price(vo)
        + ", H="
        + _tile_fmt_price(vh)
        + ", L="
        + _tile_fmt_price(vl)
        + ", C="
        + _tile_fmt_price(vc)
        + ", V="
        + vol_s
    )

    pv = tile.get("prev_ohlc") or {}
    lines.append(
        "Previous candle: O="
        + _tile_fmt_price(pv.get("o"))
        + ", H="
        + _tile_fmt_price(pv.get("h"))
        + ", L="
        + _tile_fmt_price(pv.get("l"))
        + ", C="
        + _tile_fmt_price(pv.get("c"))
        + ", RSI="
        + _tile_fmt_rsi(tile.get("prev_rsi"))
    )
    lines.append(
        "Current candle: O="
        + _tile_fmt_price(vo)
        + ", H="
        + _tile_fmt_price(vh)
        + ", L="
        + _tile_fmt_price(vl)
        + ", C="
        + _tile_fmt_price(vc)
        + ", RSI="
        + _tile_fmt_rsi(tile.get("current_rsi"))
    )
    lines.append(f"Supertrend: {tile.get('supertrend_label')}")

    atr_c = tile.get("atr_current")
    atr_a = tile.get("atr_avg200")
    atr_r = tile.get("atr_ratio")
    ratio_s = "n/a"
    if atr_r is not None:
        try:
            ratio_s = _tile_fmt_price(round(float(atr_r), 6))
        except (TypeError, ValueError):
            ratio_s = str(atr_r)
    lines.append(
        "ATR Analysis: Current="
        + _tile_fmt_price(atr_c)
        + " | Avg200="
        + _tile_fmt_price(atr_a)
        + " | Ratio="
        + ratio_s
    )

    ema = tile.get("ema200")
    lines.append(
        "Price vs EMA200: "
        + str(tile.get("price_vs_ema200") or "")
        + " (EMA="
        + _tile_fmt_price(ema)
        + ")"
    )

    bl = tile.get("breakdown_long") or {}
    bs = tile.get("breakdown_short") or {}
    # Must match evaluate_sean_jupiter_baseline_v1: long_ok = raw_long ∧ ST ∧ EMA (aggregateCandles long ≠ “RSI>52”).
    lines.append(
        "Signal Breakdown → Long="
        + _tile_lower_bool(bl.get("long_ok"))
        + " (aggregateCandles long="
        + _tile_lower_bool(bl.get("rsi_long_arm_raw"))
        + ", Supertrend="
        + _tile_lower_bool(bl.get("supertrend_bullish"))
        + ", AboveEMA="
        + _tile_lower_bool(bl.get("above_ema"))
        + ")"
    )
    lines.append(
        "Signal Breakdown → Short="
        + _tile_lower_bool(bs.get("short_ok"))
        + " (aggregateCandles short="
        + _tile_lower_bool(bs.get("rsi_short_arm_raw"))
        + ", Supertrend="
        + _tile_lower_bool(bs.get("supertrend_bearish"))
        + ", BelowEMA="
        + _tile_lower_bool(bs.get("below_ema"))
        + ")"
    )

    crsi = tile.get("current_rsi")
    rs_raw = features.get("short_signal_raw")
    rl_raw = features.get("long_signal_raw")
    lines.append(
        "Signals: short="
        + _tile_lower_bool(rs_raw)
        + " (RSI="
        + _tile_fmt_rsi(crsi)
        + "), long="
        + _tile_lower_bool(rl_raw)
    )

    vc_num = nv.get("c")
    atr_c_fmt = _tile_fmt_price(atr_c)

    # Only when policy returns trade=True — do not print "Processing …" for raw arms alone
    # (aggregateCandles short/long) or the UI reads like every bar executes (filters ignored).
    if trade and side in ("long", "short"):
        lines.append(
            "ATR-Supertrend SIGNAL → "
            + side.upper()
            + " at "
            + _tile_fmt_price(vc_num)
            + " | ATR="
            + atr_c_fmt
        )
        lines.append("Processing " + side.upper() + " signal at " + _tile_fmt_price(vc_num))

    # Filter / skip line (use en dash per operator example)
    pb = policy_blockers or []
    if isinstance(features.get("policy_blockers"), list):
        pb = [str(x) for x in features["policy_blockers"]]

    if trade:
        pass
    elif reason_code == "no_signal":
        lines.append("Filter: no aggregateCandles long/short arm – skipping entry")
    elif reason_code == "policy_filter_block":
        # Operator contract (fixed copy when Supertrend/EMA/RSI regime blocks a raw arm).
        lines.append("Filter: weak Supertrend / extreme RSI – skipping entry")
    elif reason_code == "insufficient_history":
        lines.append("Filter: insufficient bar history for EMA200/ATR – skipping entry")
    elif atr_r is not None and float(atr_r) < 0.45:
        lines.append(
            "Filter: weak ATR vs 200-bar average (ratio "
            + str(round(float(atr_r), 4))
            + ") / check RSI regime – skipping entry"
        )
    else:
        lines.append(f"Filter: {reason_code} – skipping entry")

    return "\n".join(lines)


def _ewm_mean_last(closes: list[float], span: int) -> float:
    """
    Last value of EWMA with ``span`` — matches ``pandas.Series.ewm(span=span, adjust=False).mean().iloc[-1]``
    (no pandas; safe in minimal API containers).
    """
    if len(closes) < 1:
        raise ValueError("closes empty")
    alpha = 2.0 / (float(span) + 1.0)
    ema = float(closes[0])
    for x in closes[1:]:
        ema = ema * (1.0 - alpha) + alpha * float(x)
    return ema


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
    ema200_last = _ewm_mean_last(closes, EMA_PERIOD)

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
    feat.update(
        _build_tile_payload(
            bars_asc=bars_asc,
            prev_bar=prev_bar,
            cur=cur,
            i=i,
            prev_rsi_raw=prev_rsi_raw,
            current_rsi_raw=current_rsi_raw,
            highs=highs,
            lows=lows,
            closes=closes,
            st_dir=st_dir,
            ema200_last=ema200_last,
            raw_short=raw_short,
            raw_long=raw_long,
            short_ok=short_ok,
            long_ok=long_ok,
        )
    )

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

    atr_ratio = _resolve_atr_ratio_from_features(feat)
    if atr_ratio is not None and atr_ratio < ATR_RATIO_MIN:
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="atr_ratio_below_min",
            pnl_usd=None,
            features={
                **feat,
                "policy_blockers": ["atr_ratio_below_1.35"],
            },
        )

    return SeanJupiterBaselineSignalV1(
        trade=True,
        side=side,
        reason_code=reason,
        pnl_usd=round(pnl, 8),
        features=feat,
    )
