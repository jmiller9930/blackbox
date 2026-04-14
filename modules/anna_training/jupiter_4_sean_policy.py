"""Jupiter V4 — Sean momentum perps policy (SOL 5m).

Crossover + price vs EMA21 + RSI + volume spike + ATR expected-move filter; confidence-weighted
risk/leverage. Canonical Python for Blackbox baseline when ``baseline_policy_slot`` is ``jup_v4``.

**Catalog id:** ``jupiter_4_sean_perps_v1``
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Risk & sizing (fraction of free collateral)
BASE_RISK_PCT = 0.10
MAX_RISK_PCT = 0.30
MID_RISK_PCT = 0.20
MIN_COLLATERAL_USD = 10.0

EMA_SHORT_PERIOD = 9
EMA_LONG_PERIOD = 21
RSI_PERIOD = 14
RSI_LONG_THRESHOLD = 52.0
RSI_SHORT_THRESHOLD = 48.0
VOLUME_SPIKE_MULTIPLIER = 1.20
MIN_EXPECTED_MOVE = 0.50
ATR_PERIOD = 14

# Room for EMA21 + ATR + crossover history (aligned with Grok draft)
MIN_BARS = max(EMA_LONG_PERIOD, ATR_PERIOD) + 50

REFERENCE_SOURCE = "jupiter_4_sean_policy:v1"
CATALOG_ID = "jupiter_4_sean_perps_v1"
POLICY_ENGINE_ID = "jupiter_4"
POLICY_SPEC_VERSION = "1.0"


def ema_series(series: list[float], period: int) -> list[float]:
    """EMA with SMA seed at ``period - 1`` — same recipe as JUPv3."""
    n = len(series)
    if n < period:
        return [float("nan")] * n
    ema_values = [float("nan")] * n
    ema_values[period - 1] = sum(series[:period]) / period
    alpha = 2.0 / (period + 1.0)
    for i in range(period, n):
        ema_values[i] = series[i] * alpha + ema_values[i - 1] * (1 - alpha)
    return ema_values


def rsi(series: list[float], period: int = RSI_PERIOD) -> list[float]:
    """RSI — same as JUPv3."""
    n = len(series)
    if n < period + 1:
        return [float("nan")] * n
    rsi_values = [float("nan")] * n
    gain = loss = 0.0
    for i in range(1, period + 1):
        delta = series[i] - series[i - 1]
        if delta > 0:
            gain += delta
        else:
            loss -= delta
    avg_gain = gain / period
    avg_loss = loss / period
    if avg_gain == 0 and avg_loss == 0:
        avg_gain = avg_loss = 0.001
    rs = float("inf") if avg_loss == 0 else avg_gain / avg_loss
    rsi_values[period] = 100 - (100 / (1 + rs))
    for i in range(period + 1, n):
        delta = series[i] - series[i - 1]
        cur_gain = delta if delta > 0 else 0.0
        cur_loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + cur_gain) / period
        avg_loss = (avg_loss * (period - 1) + cur_loss) / period
        rs = float("inf") if avg_loss == 0 else avg_gain / avg_loss
        rsi_values[i] = 100 - (100 / (1 + rs))
    return rsi_values


def calculate_atr(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> float:
    """True Range average over last ATR_PERIOD bars — same recipe as JUPv3."""
    if len(closes) < ATR_PERIOD + 1:
        return 0.25
    h = highs if highs is not None else closes
    l = lows if lows is not None else closes
    tr_sum = 0.0
    for i in range(1, ATR_PERIOD + 1):
        high = h[-i]
        low = l[-i]
        prev_close = closes[-i - 1]
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr_sum += max(tr1, tr2, tr3)
    return tr_sum / ATR_PERIOD


def calculate_confidence_score_v4(
    bullish_bias: bool,
    rsi_val: float,
    volume_spike: bool,
    expected_move: float,
    atr: float,
) -> int:
    """Score 0–10; RSI bands use JUPv4 thresholds (52/48)."""
    score = 2
    if (bullish_bias and rsi_val >= RSI_LONG_THRESHOLD) or (
        (not bullish_bias) and rsi_val <= RSI_SHORT_THRESHOLD
    ):
        score += 3
    if volume_spike:
        score += 2
    if expected_move >= MIN_EXPECTED_MOVE * 1.2:
        score += 2
    if atr > 0.10:
        score += 1
    return min(10, score)


def calculate_position_size_v4(
    free_collateral_usd: float,
    confidence_score: int,
    direction: str,
) -> dict[str, Any]:
    """Risk 10% / 20% / 30% of free collateral by confidence; leverage 10× / 20× / 30×."""
    if confidence_score >= 8:
        risk_pct = MAX_RISK_PCT
    elif confidence_score >= 6:
        risk_pct = MID_RISK_PCT
    else:
        risk_pct = BASE_RISK_PCT
    collateral_usd = max(MIN_COLLATERAL_USD, free_collateral_usd * risk_pct)
    if free_collateral_usd < MIN_COLLATERAL_USD:
        collateral_usd = 0.0
    if confidence_score >= 8:
        leverage = 30
    elif confidence_score >= 6:
        leverage = 20
    else:
        leverage = 10
    notional_usd = collateral_usd * leverage
    return {
        "collateral_usd": collateral_usd,
        "notional_usd": notional_usd,
        "leverage": leverage,
        "risk_pct": risk_pct,
        "direction": direction,
        "confidence_score": confidence_score,
    }


def generate_signal_from_ohlc_v4(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
) -> tuple[bool, bool, float, dict[str, Any]]:
    """Return (short_signal, long_signal, signal_price, diagnostics)."""
    diag: dict[str, Any] = {"policy_engine": POLICY_ENGINE_ID, "catalog_id": CATALOG_ID}
    n = len(closes)
    if n < MIN_BARS:
        return False, False, 0.0, {**diag, "reason": "insufficient_history", "min_bars": MIN_BARS}
    if len(highs) != n or len(lows) != n or len(volumes) != n:
        return False, False, 0.0, {**diag, "reason": "length_mismatch"}

    ema9 = ema_series(closes, EMA_SHORT_PERIOD)
    ema21 = ema_series(closes, EMA_LONG_PERIOD)
    e9 = ema9[-1]
    e21 = ema21[-1]
    e9p = ema9[-2]
    e21p = ema21[-2]
    rsi_vals = rsi(closes)
    current_rsi = rsi_vals[-1]
    current_close = closes[-1]
    if math.isnan(e9) or math.isnan(e21) or math.isnan(current_rsi):
        return False, False, 0.0, {**diag, "reason": "indicator_nan"}

    avg_volume = sum(volumes) / max(len(volumes), 1)
    candle_vol = volumes[-1]
    volume_spike = candle_vol > avg_volume * VOLUME_SPIKE_MULTIPLIER
    atr_val = calculate_atr(closes, highs, lows)
    expected_move = atr_val * 2.5

    bullish_crossover = (e9p <= e21p) and (e9 > e21)
    bearish_crossover = (e9p >= e21p) and (e9 < e21)
    price_above_ema21 = current_close > e21
    price_below_ema21 = current_close < e21

    long_gate = (
        bullish_crossover
        and price_above_ema21
        and current_rsi >= RSI_LONG_THRESHOLD
        and volume_spike
        and expected_move >= MIN_EXPECTED_MOVE
    )
    short_gate = (
        bearish_crossover
        and price_below_ema21
        and current_rsi <= RSI_SHORT_THRESHOLD
        and volume_spike
        and expected_move >= MIN_EXPECTED_MOVE
    )

    bullish_bias = e9 > e21
    bearish_bias = e9 < e21

    jupiter_v4_gates: dict[str, Any] = {
        "schema": "jupiter_v4_gates_v1",
        "rows": [
            {
                "id": "bias",
                "label": "EMA bias (9/21 + close vs 21)",
                "long_ok": bullish_bias and price_above_ema21,
                "short_ok": bearish_bias and price_below_ema21,
            },
            {
                "id": "rsi",
                "label": f"RSI (long ≥ {RSI_LONG_THRESHOLD:g}, short ≤ {RSI_SHORT_THRESHOLD:g})",
                "long_ok": current_rsi >= RSI_LONG_THRESHOLD,
                "short_ok": current_rsi <= RSI_SHORT_THRESHOLD,
            },
            {
                "id": "volume_spike",
                "label": f"Volume spike (>{VOLUME_SPIKE_MULTIPLIER:g}× avg)",
                "long_ok": volume_spike,
                "short_ok": volume_spike,
            },
            {
                "id": "crossover",
                "label": "EMA9/21 crossover",
                "long_ok": bullish_crossover,
                "short_ok": bearish_crossover,
            },
            {
                "id": "expected_move",
                "label": f"Expected move ≥ {MIN_EXPECTED_MOVE:g} (ATR×2.5)",
                "long_ok": expected_move >= MIN_EXPECTED_MOVE,
                "short_ok": expected_move >= MIN_EXPECTED_MOVE,
            },
        ],
        "long": {
            "all_ok": long_gate,
        },
        "short": {
            "all_ok": short_gate,
        },
    }

    long_signal = long_gate
    short_signal = short_gate

    diag.update(
        {
            "ema9": float(e9),
            "ema21": float(e21),
            "bullish_crossover": bullish_crossover,
            "bearish_crossover": bearish_crossover,
            "bullish_bias": bullish_bias,
            "bearish_bias": bearish_bias,
            "current_rsi": float(current_rsi),
            "atr": float(atr_val),
            "expected_move": float(expected_move),
            "avg_volume": float(avg_volume),
            "candle_volume": float(candle_vol),
            "volume_spike": volume_spike,
            "long_gate": long_gate,
            "short_gate": short_gate,
            "jupiter_v4_gates": jupiter_v4_gates,
            "short_signal_core": short_signal,
            "long_signal_core": long_signal,
        }
    )
    return short_signal, long_signal, current_close, diag


@dataclass(frozen=True)
class Jupiter4SeanPolicyResult:
    """Paper evaluation outcome — Jupiter_4."""

    trade: bool
    side: str
    reason_code: str
    pnl_usd: float | None
    features: dict[str, Any]


def _float_ohlc(bar: dict[str, Any]) -> tuple[float, float, float, float] | None:
    try:
        o = float(bar["open"])
        h = float(bar["high"])
        l = float(bar["low"])
        c = float(bar["close"])
        return o, h, l, c
    except (KeyError, TypeError, ValueError):
        return None


def _volume_from_bar(bar: dict[str, Any]) -> float:
    for k in ("volume_base", "volume"):
        v = bar.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return 0.0


def _evaluated_bar_snapshot(bars_asc: list[dict[str, Any]]) -> dict[str, Any]:
    lb = bars_asc[-1]
    snap: dict[str, Any] = {"candle_open_utc": str(lb.get("candle_open_utc") or "").strip()}
    t = _float_ohlc(lb)
    vol = _volume_from_bar(lb)
    if t:
        o, h, l, c = t
        snap["open"] = o
        snap["high"] = h
        snap["low"] = l
        snap["close"] = c
    snap["volume_base"] = float(vol)
    return snap


def evaluate_jupiter_4_sean(
    *,
    bars_asc: list[dict[str, Any]],
    free_collateral_usd: float | None = None,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> Jupiter4SeanPolicyResult:
    """Evaluate latest closed bar under Jupiter_4 entry rules."""
    if len(bars_asc) < MIN_BARS:
        return Jupiter4SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="insufficient_history",
            pnl_usd=None,
            features={
                "bars_asc_len": len(bars_asc),
                "min_bars": MIN_BARS,
                "reference": REFERENCE_SOURCE,
                "catalog_id": CATALOG_ID,
                "policy_engine": POLICY_ENGINE_ID,
            },
        )

    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    volumes: list[float] = []
    for b in bars_asc:
        t = _float_ohlc(b)
        if t is None:
            return Jupiter4SeanPolicyResult(
                trade=False,
                side="flat",
                reason_code="ohlc_parse_error",
                pnl_usd=None,
                features={"reference": REFERENCE_SOURCE, "catalog_id": CATALOG_ID},
            )
        _, h, l, c = t
        closes.append(c)
        highs.append(h)
        lows.append(l)
        volumes.append(_volume_from_bar(b))

    if free_collateral_usd is None:
        from modules.anna_training.jupiter_2_paper_collateral import (
            resolve_free_collateral_usd_for_jupiter_policy,
        )

        free_collateral_usd, br_meta = resolve_free_collateral_usd_for_jupiter_policy(
            training_state=training_state,
            ledger_db_path=ledger_db_path,
        )
    else:
        br_meta = {"source": "explicit", "free_collateral_usd": float(free_collateral_usd)}
        free_collateral_usd = float(free_collateral_usd)

    short_s, long_s, sig_px, diag = generate_signal_from_ohlc_v4(closes, highs, lows, volumes)

    feat: dict[str, Any] = {
        "reference": REFERENCE_SOURCE,
        "catalog_id": CATALOG_ID,
        "policy_version": "jupiter_4_sean_v1.0",
        "policy_engine": POLICY_ENGINE_ID,
        "free_collateral_usd": float(free_collateral_usd),
        "paper_bankroll": br_meta,
        **diag,
    }
    feat["evaluated_bar"] = _evaluated_bar_snapshot(bars_asc)

    if diag.get("reason") == "length_mismatch":
        return Jupiter4SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="ohlc_parse_error",
            pnl_usd=None,
            features=feat,
        )

    if diag.get("reason") == "insufficient_history":
        return Jupiter4SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="insufficient_history",
            pnl_usd=None,
            features=feat,
        )

    if not short_s and not long_s:
        return Jupiter4SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="jupiter_4_no_signal",
            pnl_usd=None,
            features=feat,
        )

    if short_s and long_s:
        side = "short"
        reason = "jupiter_4_short_signal"
        feat["precedence"] = "short_over_long"
    elif short_s:
        side = "short"
        reason = "jupiter_4_short_signal"
    else:
        side = "long"
        reason = "jupiter_4_long_signal"

    atr = float(diag.get("atr") or 0.0)
    bullish_bias = bool(diag.get("bullish_bias"))
    rsi_val = float(diag.get("current_rsi") or 50.0)
    vol_spike = bool(diag.get("volume_spike"))
    exp_mv = float(diag.get("expected_move") or 0.0)
    conf = calculate_confidence_score_v4(bullish_bias, rsi_val, vol_spike, exp_mv, atr)
    feat["confidence_score"] = conf
    feat["position_size_hint"] = calculate_position_size_v4(free_collateral_usd, conf, side)
    feat["signal_price"] = sig_px
    feat["parity"] = "jupiter_4_sean:evaluate_jupiter_4_sean"

    return Jupiter4SeanPolicyResult(
        trade=True,
        side=side,
        reason_code=reason,
        pnl_usd=None,
        features=feat,
    )
