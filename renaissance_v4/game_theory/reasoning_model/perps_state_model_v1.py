"""
Directive 2 — Deterministic perps **state** classification (RM layer).

Reads **only** ``indicator_context_eval_v1`` fields produced by ``build_indicator_context_eval_v1``;
does **not** recompute RSI/EMA/ATR. Does **not** influence ``decision_synthesis_v1``.
"""

from __future__ import annotations

from typing import Any

SCHEMA_PERPS_STATE_MODEL_TOP_V1 = "perps_state_model_v1"


def compute_perps_state_model_v1(
    indicator_context_eval_v1: dict[str, Any] | None,
    *,
    perps_market_inputs_available: bool = False,
) -> dict[str, Any]:
    """
    Return ``perps_state_model_v1`` document (v1 deterministic rules).

    When ``perps_market_inputs_available`` is False (current DATA path — Directive 1 audit),
    ``perps_risk_state_v1`` is the string ``not_available_v1``.
    """
    ictx = indicator_context_eval_v1 if isinstance(indicator_context_eval_v1, dict) else {}

    rsi_s = str(ictx.get("rsi_state") or "neutral")
    ema_t = str(ictx.get("ema_trend") or "neutral_trend")
    vol_st = str(ictx.get("atr_volume_state") or "normal_volatility")
    vol_part = ictx.get("volume_state")
    fl = ictx.get("support_flags_v1") if isinstance(ictx.get("support_flags_v1"), dict) else {}

    # --- trend_state (directive enums)
    trend_state = "neutral"
    if ema_t == "bullish_trend" and rsi_s not in ("exhaustion_risk", "overbought"):
        trend_state = "bullish_trend"
    elif ema_t == "bearish_trend" and rsi_s not in ("reversal_potential", "oversold"):
        trend_state = "bearish_trend"
    elif ema_t in ("bullish_trend", "bearish_trend"):
        trend_state = "neutral"

    # --- volatility_state (pass-through from engine labels)
    if vol_st == "high_volatility":
        volatility_state = "high_volatility"
    elif vol_st == "low_volatility":
        volatility_state = "low_volatility"
    else:
        volatility_state = "normal_volatility"

    conflict_detected = False
    if bool(fl.get("long")) and bool(fl.get("short")):
        conflict_detected = True
    if rsi_s == "exhaustion_risk" and ema_t == "bullish_trend":
        conflict_detected = True
    if rsi_s == "reversal_potential" and ema_t == "bearish_trend":
        conflict_detected = True

    strong_vol_participation = vol_part == "strong_participation"
    weak_vol_participation = vol_part == "weak_participation"

    structure_state = "chop"
    if vol_st == "high_volatility" and strong_vol_participation:
        structure_state = "breakout"
    elif rsi_s in ("exhaustion_risk", "overbought", "oversold") and weak_vol_participation:
        structure_state = "exhaustion"
    elif ema_t in ("bullish_trend", "bearish_trend") and not conflict_detected and vol_st != "high_volatility":
        structure_state = "trend"
    elif ema_t == "neutral_trend" or conflict_detected:
        structure_state = "chop"

    momentum_state = "weak"
    if trend_state in ("bullish_trend", "bearish_trend") and rsi_s == "neutral" and not conflict_detected:
        momentum_state = "strong"
    elif conflict_detected or (rsi_s in ("exhaustion_risk", "reversal_potential")):
        momentum_state = "diverging"
    else:
        momentum_state = "weak"

    state_flags: list[str] = []
    if (
        (bool(fl.get("long")) and ema_t == "bullish_trend")
        or (bool(fl.get("short")) and ema_t == "bearish_trend")
    ):
        state_flags.append("trend_alignment")
    if rsi_s in ("exhaustion_risk", "overbought", "oversold"):
        state_flags.append("overextension")
    if vol_st == "high_volatility":
        state_flags.append("volatility_expansion")
    if weak_vol_participation or ema_t == "neutral_trend":
        state_flags.append("low_conviction")
    if conflict_detected:
        state_flags.append("conflict_detected")

    # Bounded confidence — deterministic only (no RNG)
    agree = 0
    if trend_state != "neutral" and not conflict_detected:
        agree += 1
    if vol_st == "normal_volatility":
        agree += 1
    if vol_part is None or vol_part == "strong_participation":
        agree += 1
    conflict_n = len([f for f in state_flags if f == "conflict_detected"]) + (1 if conflict_detected else 0)
    base = 0.42 + 0.12 * agree
    if vol_st == "high_volatility":
        base -= 0.06
    if conflict_detected:
        base -= 0.14 * max(1, conflict_n)
    confidence_01 = max(0.0, min(1.0, round(base, 6)))

    inputs_used_v1 = ["rsi_state", "ema_trend", "atr_volume_state", "volume_state"]

    out: dict[str, Any] = {
        "schema": SCHEMA_PERPS_STATE_MODEL_TOP_V1,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "structure_state": structure_state,
        "momentum_state": momentum_state,
        "confidence_01": confidence_01,
        "state_flags_v1": state_flags,
        "inputs_used_v1": inputs_used_v1,
    }
    if perps_market_inputs_available:
        out["perps_risk_state_v1"] = {
            "funding_pressure": "neutral",
            "crowding_risk": "low",
            "squeeze_risk": "low",
        }
    else:
        out["perps_risk_state_v1"] = "not_available_v1"

    return out


__all__ = [
    "SCHEMA_PERPS_STATE_MODEL_TOP_V1",
    "compute_perps_state_model_v1",
]
