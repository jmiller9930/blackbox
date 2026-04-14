"""Baseline signal — **Jupiter_2** and **Jupiter_3** Sean policies.

:func:`evaluate_sean_jupiter_baseline_v1` wraps :func:`jupiter_2_sean_policy.evaluate_jupiter_2_sean`.
:func:`evaluate_sean_jupiter_baseline_v3` wraps :func:`jupiter_3_sean_policy.evaluate_jupiter_3_sean`.

Helpers ``aggregate_candles_signal_flags`` and ``rsi_trading_core`` remain for tests and demos only.
**Paper measurement** only (no venue submit).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.anna_training.jupiter_2_sean_policy import (
    ATR_RATIO_MIN,
    CATALOG_ID,
    EMA_PERIOD,
    MIN_COLLATERAL_USD,
    MIN_BARS,
    REFERENCE_SOURCE,
    evaluate_jupiter_2_sean,
    rsi as jupiter_2_rsi,
)
from modules.anna_training.jupiter_3_sean_policy import (
    CATALOG_ID as CATALOG_ID_JUPITER_3,
    evaluate_jupiter_3_sean,
)

# --- Shared constants (aggregateCandles / trading_core RSI tests) ---
RSI_PERIOD = 14
RSI_SHORT_THRESHOLD = 48
RSI_LONG_THRESHOLD = 52
PRICE_EPSILON = 0.001
RSI_EPSILON = 0.05

_J2_TO_BASELINE_REASON = {
    "jupiter_2_no_signal": "no_signal",
    "jupiter_2_atr_ratio_block": "atr_ratio_below_min",
    "jupiter_2_rsi_extreme_block": "rsi_extreme_skip",
    "jupiter_2_long_signal": "jupiter_policy_long_signal",
    "jupiter_2_short_signal": "jupiter_policy_short_signal",
    "insufficient_history": "insufficient_history",
    "ohlc_parse_error": "ohlc_parse_error",
}

_J3_TO_BASELINE_REASON = {
    "jupiter_3_no_signal": "no_signal",
    "jupiter_3_long_signal": "jupiter_policy_long_signal",
    "jupiter_3_short_signal": "jupiter_policy_short_signal",
    "insufficient_history": "insufficient_history",
    "ohlc_parse_error": "ohlc_parse_error",
}


def _resolve_atr_ratio_from_features(feat: dict[str, Any]) -> float | None:
    """
    ``tile`` from :func:`_build_operator_tile_jupiter2` carries ``atr_ratio`` and/or ``atr_current`` / ``atr_avg200``.

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


def _build_operator_tile_jupiter2(
    bars_asc: list[dict[str, Any]],
    policy_features: dict[str, Any],
) -> dict[str, Any]:
    """Operator tile from Jupiter_2 diagnostics + OHLC (RSI = policy ``jupiter_2_rsi``)."""
    prev_bar = bars_asc[-2]
    cur = bars_asc[-1]
    closes = [float(b["close"]) for b in bars_asc]
    highs = [float(b["high"]) for b in bars_asc]
    lows = [float(b["low"]) for b in bars_asc]
    rsi_s = jupiter_2_rsi(closes)
    prev_rsi = float(rsi_s[-2])
    current_rsi = float(rsi_s[-1])

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

    ema200_last = float(policy_features.get("ema200") or 0.0)
    st_bull = bool(policy_features.get("supertrend_bullish"))
    st_dir = 1 if st_bull else -1
    long_core = bool(policy_features.get("long_signal_core"))
    short_core = bool(policy_features.get("short_signal_core"))

    atr_c = float(policy_features.get("atr") or 0.0)
    avg_atr = float(policy_features.get("avg_atr_window") or 0.0)
    atr_ratio = float(policy_features.get("atr_ratio") or 0.0)

    vol = _volume_from_bar(cur)
    ts = str(cur.get("candle_open_utc") or cur.get("candle_close_utc") or "").strip()

    st_label = "BULLISH (green)" if st_bull else "BEARISH (red)"
    if cc > ema200_last:
        pvsem = "ABOVE"
    elif cc < ema200_last:
        pvsem = "BELOW"
    else:
        pvsem = "AT"

    rsi_above_52 = current_rsi > float(RSI_LONG_THRESHOLD)
    rsi_below_48 = current_rsi < float(RSI_SHORT_THRESHOLD)

    prev_candle = {"high": ph, "low": pl}
    curr_candle = {"high": ch, "low": cl}
    aggregate_short, aggregate_long = aggregate_candles_signal_flags(
        prev_candle=prev_candle,
        curr_candle=curr_candle,
        prev_rsi_raw=prev_rsi,
        current_rsi_raw=current_rsi,
    )
    agg_long_low_sweep = (pl - cl > PRICE_EPSILON)
    agg_long_rsi_rising = (current_rsi - prev_rsi > RSI_EPSILON)
    agg_long_rsi_below_52 = current_rsi < float(RSI_LONG_THRESHOLD)
    agg_short_high_sweep = (ch - ph > PRICE_EPSILON)
    agg_short_rsi_falling = (prev_rsi - current_rsi > RSI_EPSILON)
    agg_short_rsi_above_48 = current_rsi > float(RSI_SHORT_THRESHOLD)

    return {
        "tile": {
            "candle_open_utc": ts,
            "new_ohlcv": {"o": co, "h": ch, "l": cl, "c": cc, "v": vol},
            "prev_ohlc": {"o": po, "h": ph, "l": pl, "c": pc},
            "prev_rsi": prev_rsi,
            "current_rsi": current_rsi,
            "supertrend_label": st_label,
            "supertrend_direction": st_dir,
            "atr_current": atr_c,
            "atr_avg200": avg_atr if avg_atr > 0 else None,
            "atr_ratio": atr_ratio,
            "price_vs_ema200": pvsem,
            "ema200": ema200_last,
            "higher_close": higher_close,
            "lower_close": lower_close,
            "breakdown_long": {
                "supertrend_bullish": st_bull,
                "above_ema": cc > ema200_last,
                "rsi_gt_52": rsi_above_52,
                "higher_close": higher_close,
                "long_ok": long_core,
                "aggregate_candles_long": aggregate_long,
                "agg_long_components": {
                    "low_sweep": agg_long_low_sweep,
                    "rsi_rising": agg_long_rsi_rising,
                    "rsi_below_52": agg_long_rsi_below_52,
                },
            },
            "breakdown_short": {
                "supertrend_bearish": not st_bull,
                "below_ema": cc < ema200_last,
                "rsi_lt_48": rsi_below_48,
                "lower_close": lower_close,
                "short_ok": short_core,
                "aggregate_candles_short": aggregate_short,
                "agg_short_components": {
                    "high_sweep": agg_short_high_sweep,
                    "rsi_falling": agg_short_rsi_falling,
                    "rsi_above_48": agg_short_rsi_above_48,
                },
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

    Policy math and filter order (Signal Breakdown, ATR 1.35, extreme RSI): see
    ``docs/trading/jupiter_2_baseline_operator_rules.md``.
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
    vol_gate = ""
    if atr_r is not None:
        try:
            arf = float(atr_r)
            ratio_s = _tile_fmt_price(round(arf, 6))
            vol_gate = (
                " — Volatility gate: passes"
                if arf >= float(ATR_RATIO_MIN)
                else " — Volatility gate: blocked"
            )
        except (TypeError, ValueError):
            ratio_s = str(atr_r)
    lines.append(
        "ATR Analysis: Current="
        + _tile_fmt_price(atr_c)
        + " | Avg200="
        + _tile_fmt_price(atr_a)
        + " | Ratio="
        + ratio_s
        + vol_gate
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
    lines.append(
        "Signal Breakdown → Long="
        + _tile_lower_bool(bl.get("long_ok"))
        + " (Supertrend="
        + _tile_lower_bool(bl.get("supertrend_bullish"))
        + ", AboveEMA="
        + _tile_lower_bool(bl.get("above_ema"))
        + ", RSI>52="
        + _tile_lower_bool(bl.get("rsi_gt_52"))
        + ", HigherClose="
        + _tile_lower_bool(bl.get("higher_close"))
        + ")"
    )
    lines.append(
        "Signal Breakdown → Short="
        + _tile_lower_bool(bs.get("short_ok"))
        + " (Supertrend="
        + _tile_lower_bool(bs.get("supertrend_bearish"))
        + ", BelowEMA="
        + _tile_lower_bool(bs.get("below_ema"))
        + ", RSI<48="
        + _tile_lower_bool(bs.get("rsi_lt_48"))
        + ", LowerClose="
        + _tile_lower_bool(bs.get("lower_close"))
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
        lines.append("Filter: primary long and primary short both false – skipping entry")
    elif reason_code == "rsi_extreme_skip":
        lines.append(
            "Filter: extreme RSI (long blocked if RSI>75, short if RSI<25) – skipping entry"
        )
    elif reason_code == "insufficient_history":
        lines.append("Filter: insufficient bar history for EMA200/ATR – skipping entry")
    elif reason_code == "atr_ratio_below_min":
        lines.append("Filter: ATR ratio below 1.35 – skipping entry")
    else:
        lines.append(f"Filter: {reason_code} – skipping entry")

    return "\n".join(lines)


def format_baseline_jupiter_tile_narrative(
    *,
    signal_mode: str,
    features: Any,
    reason_code: str,
    trade: bool,
    side: str,
    policy_blockers: list[str] | None = None,
) -> str:
    """
    Dispatch **Jupiter_2** rich tile (``features["tile"]`` — Supertrend / EMA200 / ATR ratio) vs
    **Jupiter_3** narrative (``features["jupiter_policy_narrative"]`` or key dump).

    Persisted ``policy_evaluations`` must pass each row's ``signal_mode`` so historical v2 bars
    still show v2 rules after the operator switches the active slot to v3.
    """
    from modules.anna_training.execution_ledger import SIGNAL_MODE_JUPITER_3

    feat = features if isinstance(features, dict) else {}
    sm = (signal_mode or "").strip()
    parity = str(feat.get("parity") or "")
    is_j3 = sm == SIGNAL_MODE_JUPITER_3 or "jupiter_3" in parity
    if is_j3:
        jn = feat.get("jupiter_policy_narrative")
        if isinstance(jn, str) and jn.strip():
            return jn.strip()
        return _format_jupiter_3_operator_narrative(
            feat,
            reason_code=reason_code,
            trade=bool(trade),
            side=str(side or "flat"),
        )
    pb = policy_blockers
    if pb is None and isinstance(feat.get("policy_blockers"), list):
        pb = [str(x) for x in feat["policy_blockers"]]
    return format_jupiter_tile_narrative_v1(
        features=feat,
        reason_code=reason_code,
        trade=bool(trade),
        side=str(side or "flat"),
        policy_blockers=pb,
    )


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
    Same boolean **shape** as ``aggregateCandles`` (high/low structure + RSI swing + thresholds).

    Thresholds match **Jupiter_2** RSI bands (52 / 48), not the deprecated Drift snapshot (40 / 60).
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
    free_collateral_usd: float | None = None,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> SeanJupiterBaselineSignalV1:
    """
    Thin adapter over :func:`modules.anna_training.jupiter_2_sean_policy.evaluate_jupiter_2_sean`.

    Maps Jupiter_2 ``reason_code`` values to dashboard / ledger aliases and attaches the operator tile.

    ``free_collateral_usd`` / ``training_state`` / ``ledger_db_path`` are passed through for paper bankroll sizing
    (see ``jupiter_2_paper_collateral``). If omitted, policy resolves from paper capital.
    """
    j2 = evaluate_jupiter_2_sean(
        bars_asc=bars_asc,
        free_collateral_usd=free_collateral_usd,
        training_state=training_state,
        ledger_db_path=ledger_db_path,
    )
    mapped_reason = _J2_TO_BASELINE_REASON.get(j2.reason_code, j2.reason_code)

    feat = dict(j2.features) if j2.features else {}

    if len(bars_asc) >= MIN_BARS and mapped_reason != "ohlc_parse_error":
        try:
            feat.update(_build_operator_tile_jupiter2(bars_asc, feat))
        except (IndexError, KeyError, TypeError, ValueError):
            pass

    lg_core = bool(feat.get("long_signal_core"))
    sh_core = bool(feat.get("short_signal_core"))
    feat["short_signal_raw"] = sh_core
    feat["long_signal_raw"] = lg_core
    feat["short_signal"] = sh_core
    feat["long_signal"] = lg_core
    feat["min_notional_hint_usd"] = MIN_COLLATERAL_USD
    feat["parity"] = "jupiter_2_sean:evaluate_jupiter_2_sean"

    if mapped_reason == "atr_ratio_below_min":
        feat.setdefault("policy_blockers", ["atr_ratio_below_1.35"])
    elif mapped_reason == "rsi_extreme_skip":
        try:
            crf = float(feat.get("current_rsi", float("nan")))
        except (TypeError, ValueError):
            crf = float("nan")
        if crf > 75.0:
            feat.setdefault("policy_blockers", ["rsi_extreme_long_above_75"])
        elif crf < 25.0:
            feat.setdefault("policy_blockers", ["rsi_extreme_short_below_25"])
        else:
            feat.setdefault("policy_blockers", ["rsi_extreme"])

    return SeanJupiterBaselineSignalV1(
        trade=j2.trade,
        side=j2.side,
        reason_code=mapped_reason,
        pnl_usd=j2.pnl_usd,
        features=feat,
    )


def _format_jupiter_3_operator_narrative(
    feat: dict[str, Any],
    *,
    reason_code: str,
    trade: bool,
    side: str,
) -> str:
    """
    Sean / superjup-style operator tile — **Jupiter_3** (distinct from Jupiter_2 Supertrend tile).

    Parity with live bot log: Binance quote volume line, OHLCV, conviction filters, BOS, ATR gate,
    signal breakdown. Requires ``evaluated_bar`` + policy diagnostics (from ``evaluate_jupiter_3_sean``).
    """
    lines: list[str] = []
    eb = feat.get("evaluated_bar") if isinstance(feat.get("evaluated_bar"), dict) else {}
    v_note = str(eb.get("volume_source_note") or "")
    v_base = eb.get("volume_base")
    if v_base is None:
        try:
            v_base = float(feat.get("candle_volume")) if feat.get("candle_volume") is not None else None
        except (TypeError, ValueError):
            v_base = None

    # Binance kline path sets ``volume_source_note`` in ``_evaluated_bar_snapshot`` (jupiter_3_sean_policy):
    # strategy bars → base-asset volume; other feeds → quote. Both are real Binance when those notes are set.
    _binance_kline = frozenset({"binance_kline_quote_volume", "binance_kline_base_volume"})
    if v_note in _binance_kline and v_base is not None:
        try:
            vf = float(v_base)
            vdisp = str(int(vf)) if vf == int(vf) else _tile_fmt_price(vf)
        except (TypeError, ValueError):
            vdisp = str(v_base)
        if v_note == "binance_kline_base_volume":
            lines.append(f"Using real Binance volume (base asset): {vdisp}")
        else:
            lines.append(f"Using real Binance volume (quote USDT): {vdisp}")
    elif v_base is not None:
        try:
            vf = float(v_base)
            lines.append(
                f"Volume: {_tile_fmt_price(vf)} — not from Binance kline feed "
                "(non-strategy bar or mixed source; check price_source on bar)"
            )
        except (TypeError, ValueError):
            lines.append("Volume: unavailable")
    else:
        lines.append(
            "Binance volume: unavailable — bar missing volume_base / volume for kline evaluation"
        )

    ts = _tile_ts_iso_z(str(eb.get("candle_open_utc") or ""))
    o, h, l, c = eb.get("open"), eb.get("high"), eb.get("low"), eb.get("close")
    vv = eb.get("volume_base")
    vol_s = ""
    if vv is not None:
        try:
            fv = float(vv)
            vol_s = str(int(fv)) if fv == int(fv) else _tile_fmt_price(fv)
        except (TypeError, ValueError):
            vol_s = str(vv)
    lines.append(
        "New 5-min candle formed: Timestamp="
        + ts
        + ", O="
        + _tile_fmt_price(o)
        + ", H="
        + _tile_fmt_price(h)
        + ", L="
        + _tile_fmt_price(l)
        + ", C="
        + _tile_fmt_price(c)
        + ", V="
        + vol_s
    )

    lines.append("")
    lines.append("=== CONVICTION MOMENTUM FILTERS ===")
    lines.append("EMA9      : " + _tile_fmt_price(feat.get("ema9")))
    lines.append("EMA21     : " + _tile_fmt_price(feat.get("ema21")))
    blab = feat.get("bias_label")
    if not blab:
        bb = bool(feat.get("bullish_bias"))
        be = bool(feat.get("bearish_bias"))
        if bb and not be:
            blab = "BULLISH"
        elif be and not bb:
            blab = "BEARISH"
        else:
            blab = "NEUTRAL"
    lines.append("Bias      : " + str(blab))
    lines.append("RSI(14)   : " + _tile_fmt_rsi(feat.get("current_rsi")))

    avg_v = feat.get("avg_volume")
    cv = feat.get("candle_volume")
    vsp = bool(feat.get("volume_spike"))
    if avg_v is not None and cv is not None:
        try:
            av = float(avg_v)
            cvf = float(cv)
            cv_txt = str(int(cvf)) if cvf == int(cvf) else _tile_fmt_price(cvf)
            lines.append(
                f"Volume Spike: {cv_txt} vs Avg={av:.0f} → {'yes' if vsp else 'no'}"
            )
        except (TypeError, ValueError):
            lines.append(f"Volume Spike: (n/a) → {'yes' if vsp else 'no'}")
    else:
        lines.append(f"Volume Spike: n/a → {'yes' if vsp else 'no'}")

    lines.append("")
    # One line with ": " so dashboard label/value split is never empty; BOS = break of prior swing.
    lines.append(
        "BOS Check: close must break prior 5-bar swing high (long) or low (short); current bar excluded from that range"
    )
    lines.append("Last 5 High = " + _tile_fmt_price(feat.get("prior_swing_high")))
    lines.append("Last 5 Low  = " + _tile_fmt_price(feat.get("prior_swing_low")))
    cc = eb.get("close") if eb else None
    if cc is None:
        cc = feat.get("signal_price")
    lbos = bool(feat.get("long_bos"))
    sbos = bool(feat.get("short_bos"))
    lines.append(
        "Current price "
        + _tile_fmt_price(cc)
        + " → long BOS: "
        + ("yes" if lbos else "no")
        + ", short BOS: "
        + ("yes" if sbos else "no")
    )

    lines.append(
        "ATR(14) = "
        + _tile_fmt_price(feat.get("atr"))
        + " | Expected Move (ATR×2.5) = $"
        + _tile_fmt_price(feat.get("expected_move"))
    )

    lines.append("")
    lines.append("=== SIGNAL BREAKDOWN ===")
    lg = bool(feat.get("long_signal_core"))
    sg = bool(feat.get("short_signal_core"))
    lines.append("Long  = " + _tile_lower_bool(lg))
    lines.append("Short = " + _tile_lower_bool(sg))

    lines.append("")
    lines.append(
        "Policy: Jupiter_3 · catalog_id="
        + str(feat.get("catalog_id", CATALOG_ID_JUPITER_3))
        + " · trade="
        + _tile_lower_bool(trade)
        + " side="
        + str(side)
        + " reason_code="
        + str(reason_code)
    )

    return "\n".join(lines)


def evaluate_sean_jupiter_baseline_v3(
    *,
    bars_asc: list[dict[str, Any]],
    free_collateral_usd: float | None = None,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> SeanJupiterBaselineSignalV1:
    """
    Thin adapter over :func:`jupiter_3_sean_policy.evaluate_jupiter_3_sean` — same return shape as v1.
    """
    j3 = evaluate_jupiter_3_sean(
        bars_asc=bars_asc,
        free_collateral_usd=free_collateral_usd,
        training_state=training_state,
        ledger_db_path=ledger_db_path,
    )
    mapped_reason = _J3_TO_BASELINE_REASON.get(j3.reason_code, j3.reason_code)
    feat = dict(j3.features) if j3.features else {}
    feat["short_signal_raw"] = bool(feat.get("short_signal_core"))
    feat["long_signal_raw"] = bool(feat.get("long_signal_core"))
    feat["short_signal"] = feat["short_signal_raw"]
    feat["long_signal"] = feat["long_signal_raw"]
    feat["min_notional_hint_usd"] = MIN_COLLATERAL_USD
    feat["parity"] = "jupiter_3_sean:evaluate_jupiter_3_sean"
    feat["jupiter_policy_narrative"] = _format_jupiter_3_operator_narrative(
        feat,
        reason_code=mapped_reason,
        trade=j3.trade,
        side=str(j3.side or "flat"),
    )
    return SeanJupiterBaselineSignalV1(
        trade=j3.trade,
        side=j3.side,
        reason_code=mapped_reason,
        pnl_usd=j3.pnl_usd,
        features=feat,
    )
