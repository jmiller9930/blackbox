"""
FinQuant Unified Agent Lab — data contracts.

Builds the causal input packet used by the isolated student for each lifecycle
step. The packet is deterministic and contains:

- visible bars only
- derived mathematical features
- baseline-bounded strategy hypotheses
- memory summary from eligible prior records
"""

from __future__ import annotations

from typing import Any


SCHEMA_INPUT_PACKET = "finquant_input_packet_v1"

_STRATEGY_FAMILIES = (
    "trend_continuation",
    "pullback_continuation",
    "breakout_expansion",
    "mean_reversion_fade",
    "no_trade_guard",
)


def build_input_packet(
    *,
    case: dict[str, Any],
    step_index: int,
    visible_bars: list[dict[str, Any]],
    config: dict[str, Any],
    prior_records: list[dict[str, Any]],
) -> dict[str, Any]:
    current = visible_bars[-1] if visible_bars else {}
    prev = visible_bars[-2] if len(visible_bars) >= 2 else {}

    close = float(current.get("close", 0.0) or 0.0)
    prev_close = float(prev.get("close", close) or close)
    ema = _maybe_float(current.get("ema_20"))
    atr = _maybe_float(current.get("atr_14"))
    rsi = _maybe_float(current.get("rsi_14"))
    volume = float(current.get("volume", 0.0) or 0.0)
    prev_volume = float(prev.get("volume", volume) or volume)

    price_delta = close - prev_close
    pct_change = (price_delta / prev_close) if prev_close else 0.0
    ema_gap = (close - ema) if ema is not None else None
    volume_delta = volume - prev_volume
    ref = close if close > 0 else 1.0
    atr_pct = (atr / ref) if atr is not None else None

    memory_summary = summarize_memory_context(prior_records)
    hypotheses = build_strategy_hypotheses(
        close=close,
        prev_close=prev_close,
        ema=ema,
        atr=atr,
        rsi=rsi,
        volume=volume,
        prev_volume=prev_volume,
        resistance_level=_maybe_float(current.get("resistance_level")),
        memory_summary=memory_summary,
    )

    return {
        "schema": SCHEMA_INPUT_PACKET,
        "case_id": case.get("case_id"),
        "step_index": step_index,
        "symbol": case.get("symbol"),
        "timeframe_minutes": case.get("timeframe_minutes"),
        "runtime_data_window_months_v1": config.get("runtime_data_window_months_v1"),
        "runtime_interval_v1": config.get("runtime_interval_v1"),
        "candles_visible_v1": len(visible_bars),
        "market_math_v1": {
            "close_v1": round(close, 6),
            "prev_close_v1": round(prev_close, 6),
            "price_delta_v1": round(price_delta, 6),
            "pct_change_v1": round(pct_change, 6),
            "ema_gap_v1": round(ema_gap, 6) if ema_gap is not None else None,
            "atr_14_v1": round(atr, 6) if atr is not None else None,
            "rsi_14_v1": round(rsi, 6) if rsi is not None else None,
            "volume_delta_v1": round(volume_delta, 6),
        },
        "market_context_v1": {
            "price_above_ema_v1": ema is not None and close > ema,
            "price_up_v1": close > prev_close,
            "volume_expand_v1": volume > prev_volume,
            # ATR expansion is price-relative: >1.0% of close (calibrated to real 15m SOL-PERP).
            "atr_expanded_v1": atr_pct is not None and atr_pct > 0.0100,
            "atr_pct_v1": round(atr_pct, 6) if atr_pct is not None else None,
            "rsi_state_v1": _rsi_state(rsi),
            "volatility_state_v1": _volatility_state(atr_pct),
        },
        "memory_context_v1": memory_summary,
        "strategy_hypotheses_v1": hypotheses,
        "baseline_strategy_families_v1": list(_STRATEGY_FAMILIES),
    }


def summarize_memory_context(prior_records: list[dict[str, Any]]) -> dict[str, Any]:
    promoted = [r for r in prior_records if r.get("retrieval_enabled_v1")]
    long_count = sum(1 for r in promoted if r.get("entry_action_v1") == "ENTER_LONG")
    short_count = sum(1 for r in promoted if r.get("entry_action_v1") == "ENTER_SHORT")
    no_trade_count = sum(1 for r in promoted if r.get("entry_action_v1") == "NO_TRADE")
    best_grade = "UNKNOWN"
    if any(r.get("grade_v1") == "PASS" for r in promoted):
        best_grade = "PASS"
    elif any(r.get("grade_v1") == "FAIL" for r in promoted):
        best_grade = "FAIL"

    return {
        "matched_record_count_v1": len(promoted),
        "matched_record_ids_v1": [str(r.get("record_id")) for r in promoted],
        "long_bias_count_v1": long_count,
        "short_bias_count_v1": short_count,
        "no_trade_bias_count_v1": no_trade_count,
        "best_grade_v1": best_grade,
        "memory_influence_available_v1": len(promoted) > 0,
    }


def build_strategy_hypotheses(
    *,
    close: float,
    prev_close: float,
    ema: float | None,
    atr: float | None,
    rsi: float | None,
    volume: float,
    prev_volume: float,
    resistance_level: float | None,
    memory_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    ref = close if close > 0 else 1.0
    atr_pct = (atr / ref) if atr is not None else None

    price_up = close > prev_close
    price_above_ema = ema is not None and close > ema
    volume_expand = volume > prev_volume
    # ATR expansion: price-relative thresholds calibrated to real 15m SOL-PERP ATR% distribution.
    atr_expand = atr_pct is not None and atr_pct > 0.0100
    atr_near = atr_pct is not None and atr_pct > 0.0050
    memory_long = memory_summary.get("long_bias_count_v1", 0) > 0

    trend_score = 0.0
    if price_up:
        trend_score += 0.25
    if price_above_ema:
        trend_score += 0.2
    if rsi is not None and 50.0 < rsi < 70.0:
        trend_score += 0.2
    if volume_expand:
        trend_score += 0.15
    if atr_expand:
        trend_score += 0.1
    if memory_long:
        trend_score += 0.1

    breakout_score = 0.0
    if resistance_level is not None and close > resistance_level:
        breakout_score += 0.5
    if atr_expand:
        breakout_score += 0.15
    if volume_expand:
        breakout_score += 0.15
    if rsi is not None and rsi > 58.0:
        breakout_score += 0.1
    if memory_long:
        breakout_score += 0.1

    mean_reversion_score = 0.0
    if rsi is not None and rsi < 40.0:
        mean_reversion_score += 0.35
    if ema is not None and close < ema:
        mean_reversion_score += 0.2
    if atr_pct is not None and atr_pct < 0.0040:
        mean_reversion_score += 0.1

    no_trade_score = 0.2
    if atr_pct is None or atr_pct < 0.0030:
        no_trade_score += 0.25
    if rsi is not None and 47.0 <= rsi <= 53.0:
        no_trade_score += 0.15
    if prev_close > 0 and abs(close - prev_close) / prev_close < 0.001:
        no_trade_score += 0.15
    if memory_summary.get("no_trade_bias_count_v1", 0) > 0:
        no_trade_score += 0.1

    pullback_score = 0.0
    if price_above_ema and not price_up and rsi is not None and rsi >= 48.0:
        pullback_score += 0.35
    if atr_near:
        pullback_score += 0.15
    if memory_long:
        pullback_score += 0.1

    return [
        _hypothesis("trend_continuation", "ENTER_LONG", trend_score),
        _hypothesis("pullback_continuation", "ENTER_LONG", pullback_score),
        _hypothesis("breakout_expansion", "ENTER_LONG", breakout_score),
        _hypothesis("mean_reversion_fade", "ENTER_SHORT", mean_reversion_score),
        _hypothesis("no_trade_guard", "NO_TRADE", no_trade_score),
    ]


def _hypothesis(strategy_family: str, action: str, score: float) -> dict[str, Any]:
    return {
        "strategy_family_v1": strategy_family,
        "action_v1": action,
        "score_v1": round(max(0.0, min(score, 1.0)), 6),
    }


def _rsi_state(rsi: float | None) -> str:
    if rsi is None:
        return "unknown"
    if rsi >= 70.0:
        return "overbought"
    if rsi <= 40.0:
        return "oversold"
    if 50.0 < rsi < 70.0:
        return "bullish_range"
    return "neutral"


def _volatility_state(atr_pct: float | None) -> str:
    """Classify volatility using price-relative ATR% (calibrated to real 15m SOL-PERP)."""
    if atr_pct is None:
        return "unknown"
    if atr_pct >= 0.0200:
        return "expanded"
    if atr_pct < 0.0030:
        return "contracted"
    return "normal"


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
