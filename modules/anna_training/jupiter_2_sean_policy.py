"""Jupiter_2 — Sean **Trading Policy v1.0** (SOL-USDC perps, Jupiter Perps).

Paper / monitoring parity with the operator’s **TypeScript bot** spec: Supertrend (10, 3),
EMA200, RSI 14, simple TR ATR (not Wilder), ATR ratio vs 200-bar average (≥ 1.35 to allow
entries), dynamic sizing hints — **no venue execution** in this module.

**Catalog id:** ``jupiter_2_sean_perps_v1``

Exit / trailing / lifecycle enforcement live in ``modules/anna_training/jupiter_2_baseline_lifecycle.py``
and ``baseline_ledger_bridge`` (paper). This module remains **entry + sizing** for the evaluator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ==================== TRADING POLICY CONSTANTS (spec) ====================
BASE_RISK_PCT = 0.01
MAX_RISK_PCT = 0.03
ATR_PERIOD = 14
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0
EMA_PERIOD = 200
RSI_PERIOD = 14
RSI_LONG_THRESHOLD = 52.0
RSI_SHORT_THRESHOLD = 48.0
CONFIDENCE_THRESHOLD = 0.001  # Pyth — ingest layer; documented for parity
SLIPPAGE_PCT = 0.02
CLOSE_SLIPPAGE_PCT = 0.08
SPREAD_BUFFER_PCT = 0.002
MIN_COLLATERAL_USD = 10.0
MOD_DEBOUNCE_MS = 5000

ATR_RATIO_MIN = 1.35  # spec: skip entries when atr_ratio < 1.35

MIN_BARS = EMA_PERIOD + ATR_PERIOD + 2  # 216 — matches generate_signal guard

REFERENCE_SOURCE = "jupiter_sean_policy:v1.0:SOL_perp_Jupiter_2+TypeScript_ports"
CATALOG_ID = "jupiter_2_sean_perps_v1"

# --- Application-wide identity (baseline, ledger, dashboard) ---
# Use this string anywhere you need to answer “which Jupiter policy engine?”
# (Contrast: env ``BASELINE_LEDGER_SIGNAL_MODE=sean_jupiter_v1`` is a legacy *mode name*, not “policy v1”.)
POLICY_ENGINE_ID = "jupiter_2"
# Sean’s written spec / catalog revision (1.0) — not the same thing as “Jupiter_1 vs Jupiter_2”.
POLICY_SPEC_VERSION = "1.0"

POLICY_NOTES = (
    "Virtual SL/TP: initial ±1.6×ATR / ±4.0×ATR, breakeven after +0.2%, trailing; "
    "market orders only; one position; 5m debounce on trailing — see bot runtime, not this evaluator."
)


def calculate_atr(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> float:
    """True Range average over last ATR_PERIOD bars — spec port (simple mean TR)."""
    if len(closes) < ATR_PERIOD + 1:
        return 0.02
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


def ema(series: list[float], period: int = EMA_PERIOD) -> list[float]:
    """EMA — spec port (SMA seed at index period-1)."""
    n = len(series)
    if n < period:
        return [float("nan")] * n
    ema_values = [float("nan")] * n
    alpha = 2.0 / (period + 1.0)
    ema_values[period - 1] = sum(series[:period]) / period
    for i in range(period, n):
        ema_values[i] = series[i] * alpha + ema_values[i - 1] * (1 - alpha)
    return ema_values


def rsi(series: list[float], period: int = RSI_PERIOD) -> list[float]:
    """RSI — spec port."""
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


class Supertrend:
    """Supertrend (SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER) — spec stateful update."""

    def __init__(self) -> None:
        self.trend = 1
        self.final_upper_band = 0.0
        self.final_lower_band = 0.0

    def update(self, closes: list[float], highs: list[float], lows: list[float]) -> bool:
        if len(closes) < SUPERTREND_PERIOD:
            return self.trend == 1

        i = len(closes) - 1
        atr = calculate_atr(closes, highs, lows)
        hl2 = (highs[i] + lows[i]) / 2
        upper_band = hl2 + SUPERTREND_MULTIPLIER * atr
        lower_band = hl2 - SUPERTREND_MULTIPLIER * atr

        if self.trend == 1:
            lower_band = max(lower_band, self.final_lower_band)
        else:
            upper_band = min(upper_band, self.final_upper_band)

        current_close = closes[i]

        if self.trend == 1 and current_close < lower_band:
            self.trend = -1
        elif self.trend == -1 and current_close > upper_band:
            self.trend = 1

        self.final_upper_band = upper_band
        self.final_lower_band = lower_band
        return self.trend == 1


def _supertrend_bullish_at_end(closes: list[float], highs: list[float], lows: list[float]) -> bool:
    """Replay bars so Supertrend state matches sequential TypeScript updates."""
    st = Supertrend()
    n = len(closes)
    if n < SUPERTREND_PERIOD:
        return True
    for j in range(SUPERTREND_PERIOD - 1, n):
        st.update(closes[: j + 1], highs[: j + 1], lows[: j + 1])
    return st.trend == 1


def _float_ohlc(bar: dict[str, Any]) -> tuple[float, float, float, float] | None:
    try:
        o = float(bar["open"])
        h = float(bar["high"])
        l = float(bar["low"])
        c = float(bar["close"])
        return o, h, l, c
    except (KeyError, TypeError, ValueError):
        return None


def generate_signal_from_ohlc(
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> tuple[bool, bool, float, dict[str, Any]]:
    """
    Returns (short_signal, long_signal, signal_price, diagnostics).

    Matches spec ``generate_signal`` after OHLC extraction; adds diagnostics for UI.
    """
    diag: dict[str, Any] = {}
    if len(closes) < EMA_PERIOD + ATR_PERIOD + 2:
        return False, False, 0.0, {"reason": "insufficient_history", "min_bars": MIN_BARS}

    current_close = closes[-1]
    prev_close = closes[-2]

    is_bullish = _supertrend_bullish_at_end(closes, highs, lows)
    ema200_s = ema(closes)
    ema200_last = ema200_s[-1]
    if math.isnan(ema200_last):
        return False, False, 0.0, {"reason": "ema_nan"}

    rsi_values = rsi(closes)
    current_rsi = rsi_values[-1]
    if current_rsi != current_rsi or math.isnan(current_rsi):
        return False, False, 0.0, {"reason": "rsi_nan"}

    long_signal = (
        is_bullish
        and current_close > ema200_last
        and current_rsi > RSI_LONG_THRESHOLD
        and current_close > prev_close
    )
    short_signal = (
        not is_bullish
        and current_close < ema200_last
        and current_rsi < RSI_SHORT_THRESHOLD
        and current_close < prev_close
    )

    atr = calculate_atr(closes, highs, lows)
    if len(closes) >= 200:
        avg_atr = calculate_atr(closes[-214:-14], highs[-214:-14], lows[-214:-14])
    else:
        avg_atr = atr
    atr_ratio = atr / avg_atr if avg_atr and avg_atr > 0 else 1.0

    diag.update(
        {
            "supertrend_bullish": is_bullish,
            "ema200": float(ema200_last),
            "current_rsi": float(current_rsi),
            "atr": float(atr),
            "avg_atr_window": float(avg_atr),
            "atr_ratio": float(atr_ratio),
            "long_signal_core": long_signal,
            "short_signal_core": short_signal,
        }
    )

    if atr_ratio < ATR_RATIO_MIN:
        diag["block"] = "atr_ratio_below_1_35"
        return False, False, 0.0, diag
    if (short_signal and current_rsi < 25) or (long_signal and current_rsi > 75):
        diag["block"] = "rsi_extreme"
        return False, False, 0.0, diag

    return short_signal, long_signal, current_close, diag


def calculate_position_size(
    free_collateral_usd: float,
    atr_ratio: float,
    direction: str,
) -> dict[str, Any]:
    """Spec: dynamic risk + leverage from ATR ratio."""
    if atr_ratio > 1.5:
        risk_pct = MAX_RISK_PCT
    elif atr_ratio > 1.2:
        risk_pct = 0.02
    else:
        risk_pct = BASE_RISK_PCT

    risk_dollars = free_collateral_usd * risk_pct
    collateral_usd = max(MIN_COLLATERAL_USD, risk_dollars)

    if atr_ratio > 1.5:
        leverage = 33
    elif atr_ratio > 1.2:
        leverage = 24
    else:
        leverage = 15

    notional_usd = collateral_usd * leverage

    return {
        "collateral_usd": collateral_usd,
        "notional_usd": notional_usd,
        "leverage": leverage,
        "risk_pct": risk_pct,
        "direction": direction,
    }


@dataclass(frozen=True)
class Jupiter2SeanPolicyResult:
    """Paper evaluation outcome — Jupiter_2."""

    trade: bool
    side: str  # "long" | "short" | "flat"
    reason_code: str
    pnl_usd: float | None
    features: dict[str, Any]


def evaluate_jupiter_2_sean(
    *,
    bars_asc: list[dict[str, Any]],
    free_collateral_usd: float | None = None,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> Jupiter2SeanPolicyResult:
    """
    Evaluate **latest** closed bar (``bars_asc[-1]``) under Jupiter_2 entry rules.

    ``bars_asc`` rows: ``open``, ``high``, ``low``, ``close`` (float-like); optional
    ``candle_open_utc``, ``tick_count``, etc. ignored for signal math.

    ``free_collateral_usd`` drives ``calculate_position_size``. If omitted, resolves from
    paper capital (see ``jupiter_2_paper_collateral.resolve_free_collateral_usd_for_jupiter_policy``),
    not a hardcoded stub.
    """
    if len(bars_asc) < MIN_BARS:
        return Jupiter2SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="insufficient_history",
            pnl_usd=None,
            features={
                "bars_asc_len": len(bars_asc),
                "min_bars": MIN_BARS,
                "reference": REFERENCE_SOURCE,
                "catalog_id": CATALOG_ID,
            },
        )

    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    for b in bars_asc:
        t = _float_ohlc(b)
        if t is None:
            return Jupiter2SeanPolicyResult(
                trade=False,
                side="flat",
                reason_code="ohlc_parse_error",
                pnl_usd=None,
                features={"reference": REFERENCE_SOURCE},
            )
        _, h, l, c = t
        closes.append(c)
        highs.append(h)
        lows.append(l)

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

    short_s, long_s, sig_px, diag = generate_signal_from_ohlc(closes, highs, lows)
    atr_ratio = float(diag.get("atr_ratio", 1.0))

    feat: dict[str, Any] = {
        "reference": REFERENCE_SOURCE,
        "catalog_id": CATALOG_ID,
        "policy_version": "jupiter_2_sean_v1.0",
        "confidence_threshold_note": CONFIDENCE_THRESHOLD,
        "free_collateral_usd": float(free_collateral_usd),
        "paper_bankroll": br_meta,
        **diag,
    }

    if diag.get("block") == "atr_ratio_below_1_35":
        feat["reason_detail"] = "atr_ratio_below_1_35"
        return Jupiter2SeanPolicyResult(
            trade=False, side="flat", reason_code="jupiter_2_atr_ratio_block", pnl_usd=None, features=feat
        )
    if diag.get("block") == "rsi_extreme":
        feat["reason_detail"] = "rsi_extreme"
        return Jupiter2SeanPolicyResult(
            trade=False, side="flat", reason_code="jupiter_2_rsi_extreme_block", pnl_usd=None, features=feat
        )

    if not short_s and not long_s:
        return Jupiter2SeanPolicyResult(
            trade=False,
            side="flat",
            reason_code="jupiter_2_no_signal",
            pnl_usd=None,
            features=feat,
        )

    if short_s and long_s:
        side = "short"
        reason = "jupiter_2_short_signal"
        feat["precedence"] = "short_over_long"
    elif short_s:
        side = "short"
        reason = "jupiter_2_short_signal"
    else:
        side = "long"
        reason = "jupiter_2_long_signal"

    feat["position_size_hint"] = calculate_position_size(free_collateral_usd, atr_ratio, side)
    feat["signal_price"] = sig_px

    return Jupiter2SeanPolicyResult(
        trade=True,
        side=side,
        reason_code=reason,
        pnl_usd=None,
        features=feat,
    )


def format_jupiter_2_snapshot_text(res: Jupiter2SeanPolicyResult) -> str:
    """Compact operator-readable block for logs / UI."""
    f = res.features
    lines = [
        f"Policy: {REFERENCE_SOURCE}",
        f"catalog_id={CATALOG_ID}",
        f"trade={res.trade} side={res.side} reason_code={res.reason_code}",
    ]
    if isinstance(f.get("atr_ratio"), (int, float)):
        lines.append(f"atr_ratio={f.get('atr_ratio')}")
    if res.trade and isinstance(f.get("position_size_hint"), dict):
        p = f["position_size_hint"]
        lines.append(
            f"sizing: leverage={p.get('leverage')} risk_pct={p.get('risk_pct')} "
            f"collateral_usd≈{p.get('collateral_usd')}"
        )
    lines.append(POLICY_NOTES[:200] + "…")
    return "\n".join(lines)
