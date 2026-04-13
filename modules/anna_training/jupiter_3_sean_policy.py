"""Jupiter_3 — Sean **conviction / BOS** baseline (SOL perps, 5m), ported from ``vscode-test/superjup.ts.old``.

EMA9/EMA21 bias, RSI 14 (55/45), volume spike vs rolling mean, break of prior swing (5-bar lookback),
``expected_move = ATR × 2.5`` vs ``MIN_EXPECTED_MOVE`` (0.80 USD-class threshold — see note).

**Catalog id:** ``jupiter_3_sean_perps_v1``

Paper / monitoring only in this module (no venue execution). Exit / trailing parity with the TS bot
(2×/3× ATR, breakeven, etc.) belongs in ``jupiter_3_baseline_lifecycle.py`` when wired — not evaluated here.

**BOS vs reference TS:** In ``superjup.ts.old``, ``recentHigh`` includes the current bar's high, so
``close > recentHigh`` cannot hold on ordinary OHLC. We define BOS as breakout vs **prior five completed
bars** (exclude current bar from the max/min pool), which matches the intended “break structure” idea.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ==================== TRADING POLICY CONSTANTS (superjup.ts.old) ====================
BASE_RISK_PCT = 0.01
MAX_RISK_PCT = 0.03
MIN_COLLATERAL_USD = 10.0

EMA_SHORT_PERIOD = 9
EMA_LONG_PERIOD = 21
RSI_PERIOD = 14
RSI_LONG_THRESHOLD = 55.0
RSI_SHORT_THRESHOLD = 45.0
VOLUME_SPIKE_MULTIPLIER = 1.5
BOS_LOOKBACK_CANDLES = 5
MIN_EXPECTED_MOVE = 0.80
ATR_PERIOD = 14

MIN_BARS = EMA_LONG_PERIOD + ATR_PERIOD + 10  # room for EMA21 + ATR + BOS prior window

REFERENCE_SOURCE = "superjup_trading_bot:conviction_bos:v1 → jupiter_3_sean_policy"
CATALOG_ID = "jupiter_3_sean_perps_v1"
POLICY_ENGINE_ID = "jupiter_3"
POLICY_SPEC_VERSION = "1.0"


def calculate_atr(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> float:
    """True Range average over last ATR_PERIOD bars — same recipe as TS ``calculateATR`` (simple mean TR)."""
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


def ema_series(series: list[float], period: int) -> list[float]:
    """EMA with SMA seed at ``period - 1`` — matches TS ``ema``."""
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
    """RSI — same as ``jupiter_2_sean_policy.rsi``."""
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
    """Prefer ``volume_base`` (market_bars); fall back to ``volume`` or 0."""
    for k in ("volume_base", "volume"):
        v = bar.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    t = bar.get("tick_count")
    if t is not None:
        try:
            return float(int(t))
        except (TypeError, ValueError):
            pass
    return 0.0


def _prior_swing_levels(
    highs: list[float],
    lows: list[float],
) -> tuple[float | None, float | None]:
    """
    Max high / min low over the **five bars before the current (last) bar**.

    Index slice ``[-BOS-1:-1]`` = five completed bars when length >= BOS + 2.
    """
    if len(highs) < BOS_LOOKBACK_CANDLES + 1 or len(lows) < BOS_LOOKBACK_CANDLES + 1:
        return None, None
    ph = highs[-(BOS_LOOKBACK_CANDLES + 1) : -1]
    pl = lows[-(BOS_LOOKBACK_CANDLES + 1) : -1]
    return max(ph), min(pl)


def generate_signal_from_ohlc_v3(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
) -> tuple[bool, bool, float, dict[str, Any]]:
    """
    Returns (short_signal, long_signal, signal_price, diagnostics).

    ``volumes`` must align index-wise with OHLC (same length). Missing volume → 0.0 for that bar.
    """
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
    current_close = closes[-1]
    if math.isnan(e9) or math.isnan(e21):
        return False, False, 0.0, {**diag, "reason": "ema_nan"}

    rsi_vals = rsi(closes)
    current_rsi = rsi_vals[-1]
    if current_rsi != current_rsi or math.isnan(current_rsi):
        return False, False, 0.0, {**diag, "reason": "rsi_nan"}

    avg_volume = sum(volumes) / max(len(volumes), 1)
    candle_vol = volumes[-1]
    volume_spike = candle_vol > avg_volume * VOLUME_SPIKE_MULTIPLIER

    bullish_bias = e9 > e21 and current_close > e21
    bearish_bias = e9 < e21 and current_close < e21

    atr = calculate_atr(closes, highs, lows)
    expected_move = atr * 2.5

    prior_high, prior_low = _prior_swing_levels(highs, lows)
    if prior_high is None or prior_low is None:
        return False, False, 0.0, {**diag, "reason": "insufficient_bos_window"}

    # BOS: close clears **prior** 5-bar range (see module docstring).
    long_bos = current_close > prior_high
    short_bos = current_close < prior_low

    long_signal = (
        bullish_bias
        and current_rsi >= RSI_LONG_THRESHOLD
        and volume_spike
        and long_bos
        and expected_move >= MIN_EXPECTED_MOVE
    )
    short_signal = (
        bearish_bias
        and current_rsi <= RSI_SHORT_THRESHOLD
        and volume_spike
        and short_bos
        and expected_move >= MIN_EXPECTED_MOVE
    )

    diag.update(
        {
            "ema9": float(e9),
            "ema21": float(e21),
            "bullish_bias": bullish_bias,
            "bearish_bias": bearish_bias,
            "current_rsi": float(current_rsi),
            "atr": float(atr),
            "expected_move": float(expected_move),
            "avg_volume": float(avg_volume),
            "candle_volume": float(candle_vol),
            "volume_spike": volume_spike,
            "prior_swing_high": float(prior_high),
            "prior_swing_low": float(prior_low),
            "long_bos": long_bos,
            "short_bos": short_bos,
            "long_signal_core": long_signal,
            "short_signal_core": short_signal,
        }
    )
    return short_signal, long_signal, current_close, diag


def calculate_confidence_score(
    bullish_bias: bool,
    rsi_val: float,
    volume_spike: bool,
    expected_move: float,
    atr: float,
) -> int:
    """Mirrors TS ``calculateConfidenceScore``."""
    score = 2
    if (bullish_bias and rsi_val >= RSI_LONG_THRESHOLD) or ((not bullish_bias) and rsi_val <= RSI_SHORT_THRESHOLD):
        score += 3
    if volume_spike:
        score += 2
    if expected_move >= MIN_EXPECTED_MOVE * 1.2:
        score += 2
    if atr > 0.10:
        score += 1
    return min(10, score)


def calculate_position_size_v3(
    free_collateral_usd: float,
    confidence_score: int,
    direction: str,
) -> dict[str, Any]:
    """Leverage 10 / 20 / 30 from TS ``processSignals``; collateral max(MIN, free × BASE_RISK_PCT)."""
    risk_pct = BASE_RISK_PCT
    collateral_usd = max(MIN_COLLATERAL_USD, free_collateral_usd * risk_pct)
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


@dataclass(frozen=True)
class Jupiter3SeanPolicyResult:
    """Paper evaluation outcome — Jupiter_3."""

    trade: bool
    side: str
    reason_code: str
    pnl_usd: float | None
    features: dict[str, Any]


def evaluate_jupiter_3_sean(
    *,
    bars_asc: list[dict[str, Any]],
    free_collateral_usd: float | None = None,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> Jupiter3SeanPolicyResult:
    """
    Evaluate **latest** closed bar (``bars_asc[-1]``) under Jupiter_3 entry rules.

    Each bar may include ``volume_base`` or ``volume`` for volume spike; if all zeros, ``volume_spike`` is False.
    """
    if len(bars_asc) < MIN_BARS:
        return Jupiter3SeanPolicyResult(
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
            return Jupiter3SeanPolicyResult(
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

    short_s, long_s, sig_px, diag = generate_signal_from_ohlc_v3(closes, highs, lows, volumes)

    feat: dict[str, Any] = {
        "reference": REFERENCE_SOURCE,
        "catalog_id": CATALOG_ID,
        "policy_version": "jupiter_3_sean_v1.0",
        "policy_engine": POLICY_ENGINE_ID,
        "free_collateral_usd": float(free_collateral_usd),
        "paper_bankroll": br_meta,
        **diag,
    }

    if diag.get("reason") == "length_mismatch":
        return Jupiter3SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="ohlc_parse_error",
            pnl_usd=None,
            features=feat,
        )

    if diag.get("reason") in ("insufficient_history", "insufficient_bos_window"):
        return Jupiter3SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="insufficient_history",
            pnl_usd=None,
            features=feat,
        )

    if not short_s and not long_s:
        return Jupiter3SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="jupiter_3_no_signal",
            pnl_usd=None,
            features=feat,
        )

    if short_s and long_s:
        side = "short"
        reason = "jupiter_3_short_signal"
        feat["precedence"] = "short_over_long"
    elif short_s:
        side = "short"
        reason = "jupiter_3_short_signal"
    else:
        side = "long"
        reason = "jupiter_3_long_signal"

    atr = float(diag.get("atr") or 0.0)
    bullish_bias = bool(diag.get("bullish_bias"))
    rsi_val = float(diag.get("current_rsi") or 50.0)
    vol_spike = bool(diag.get("volume_spike"))
    exp_mv = float(diag.get("expected_move") or 0.0)
    conf = calculate_confidence_score(bullish_bias, rsi_val, vol_spike, exp_mv, atr)
    feat["confidence_score"] = conf
    feat["position_size_hint"] = calculate_position_size_v3(free_collateral_usd, conf, side)
    feat["signal_price"] = sig_px

    return Jupiter3SeanPolicyResult(
        trade=True,
        side=side,
        reason_code=reason,
        pnl_usd=None,
        features=feat,
    )


def format_jupiter_3_snapshot_text(res: Jupiter3SeanPolicyResult) -> str:
    """Compact operator-readable block for logs / UI."""
    f = res.features
    lines = [
        f"Policy: {REFERENCE_SOURCE}",
        f"catalog_id={CATALOG_ID}",
        f"trade={res.trade} side={res.side} reason_code={res.reason_code}",
    ]
    if res.trade and isinstance(f.get("position_size_hint"), dict):
        p = f["position_size_hint"]
        lines.append(
            f"sizing: leverage={p.get('leverage')} conf={p.get('confidence_score')} "
            f"collateral_usd≈{p.get('collateral_usd')}"
        )
    return "\n".join(lines)
