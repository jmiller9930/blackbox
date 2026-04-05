"""
Authoritative trend context for operator dashboards: EMA reference, regime tags, trade alignment.

Alignment is computed server-side only — UI must not infer business rules from raw OHLC alone.
"""

from __future__ import annotations

from typing import Any

from modules.anna_training.chart_overlay import _bar_index_for_time, _bars_chronological, _parse_iso
from modules.anna_training.quantitative_evaluation_layer.checkpoint_config import load_survival_config
from modules.anna_training.quantitative_evaluation_layer.regime_tags_v1 import (
    TREND_DOWN,
    TREND_FLAT,
    TREND_UP,
    regime_tags_v1_from_bar,
)

SCHEMA = "trend_context_v2"
EMA_PERIODS_DEFAULT = (20, 50, 200)
PRIMARY_TREND_PERIOD = 50

ALIGNMENT_RULE = (
    "Bar-level trend_bucket from regime_tags_v1 (single-bar open→close direction). "
    "long + trend_up, short + trend_down => with_trend; "
    "long + trend_down, short + trend_up => against_trend; "
    "trend_flat or unrecognized side => neutral_trend or unknown."
)


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        v = float(x)
        return v if v == v else None  # noqa: PLR0124
    except (TypeError, ValueError):
        return None


def _bar_unix_open(b: dict[str, Any]) -> int | None:
    co = str(b.get("candle_open_utc") or "").strip()
    if not co:
        return None
    dt = _parse_iso(co)
    if not dt:
        return None
    return int(dt.timestamp())


def ema_from_closes(closes: list[float], period: int) -> list[float | None]:
    """EMA aligned 1:1 with closes; first value seeds with first close."""
    n = len(closes)
    if n == 0 or period < 1:
        return [None] * n
    alpha = 2.0 / (period + 1)
    out: list[float | None] = [None] * n
    ema = closes[0]
    out[0] = ema
    for i in range(1, n):
        ema = alpha * closes[i] + (1.0 - alpha) * ema
        out[i] = ema
    return out


def interpret_side_vs_trend(side: str | None, trend_bucket: str | None) -> tuple[str, str]:
    """Returns (alignment, short interpretation)."""
    s = (side or "").strip().lower()
    t = (trend_bucket or "").strip().lower()
    if t not in (TREND_UP, TREND_DOWN, TREND_FLAT):
        return "unknown", "trend bucket unavailable for entry bar"
    if s == "long":
        if t == TREND_UP:
            return "with_trend", "long while bar trend is up"
        if t == TREND_DOWN:
            return "against_trend", "long while bar trend is down"
        return "neutral_trend", "long while bar trend is flat"
    if s == "short":
        if t == TREND_DOWN:
            return "with_trend", "short while bar trend is down"
        if t == TREND_UP:
            return "against_trend", "short while bar trend is up"
        return "neutral_trend", "short while bar trend is flat"
    return "unknown", "side not long/short"


def _regime_params() -> dict[str, float]:
    cfg = load_survival_config()
    rv = cfg.get("regime_v1") or {}
    return {
        "vol_low_below": float(rv.get("vol_low_below", 0.003)),
        "vol_mid_below": float(rv.get("vol_mid_below", 0.012)),
        "flat_abs_pct": float(rv.get("flat_abs_pct", 0.0005)),
    }


def _event_gate_state(trades: list[dict[str, Any]], market_event_id: str) -> str | None:
    for t in trades:
        if str(t.get("market_event_id") or "").strip() != market_event_id:
            continue
        ctx = t.get("context_snapshot")
        if isinstance(ctx, dict) and ctx.get("gate_state"):
            return str(ctx.get("gate_state"))
    return None


def build_trend_context(
    *,
    history_bars: list[dict[str, Any]],
    market_event_id: str,
    trades_enriched: list[dict[str, Any]],
    ema_period: int = 50,
    ema_periods: tuple[int, ...] = EMA_PERIODS_DEFAULT,
) -> dict[str, Any]:
    """
    EMA reference layers (20/50/200 on closes), regime_tags_v1 per bar, trade alignment at entry bar.

    ``history_bars`` is newest-first (API order); internally reversed to chronological.
    ``trend_reference_series`` duplicates EMA50 points for backward compatibility.
    """
    rp = _regime_params()
    bars = _bars_chronological(history_bars)
    n = len(bars)
    if n == 0:
        return {
            "schema": SCHEMA,
            "ema_period": ema_period,
            "ema_periods": list(ema_periods),
            "ema_primary_period": PRIMARY_TREND_PERIOD,
            "alignment_rule": ALIGNMENT_RULE,
            "trend_reference_layers": [],
            "trend_reference_series": [],
            "regime_tags_by_bar": [],
            "event_bar_index": None,
            "event_bar_regime_tags": None,
            "trade_trend_alignments": [],
        }

    closes: list[float] = []
    last: float | None = None
    for b in bars:
        c = _f(b.get("close"))
        if c is None and last is not None:
            c = last
        if c is None:
            c = 0.0
        else:
            last = c
        closes.append(c)

    trend_reference_layers: list[dict[str, Any]] = []
    for period in ema_periods:
        ema_vals = ema_from_closes(closes, period)
        pts: list[dict[str, Any]] = []
        for i, b in enumerate(bars):
            tu = _bar_unix_open(b)
            ev = ema_vals[i]
            if tu is not None and ev is not None:
                pts.append({"time": tu, "value": float(ev)})
        role = "fast_trend"
        if period == PRIMARY_TREND_PERIOD:
            role = "primary_trend"
        elif period == 200:
            role = "slow_trend"
        trend_reference_layers.append(
            {
                "period": period,
                "label": f"EMA{period}",
                "role": role,
                "points": pts,
            }
        )
    primary_layer = next((x for x in trend_reference_layers if x["period"] == PRIMARY_TREND_PERIOD), None)
    trend_reference_series: list[dict[str, Any]] = list(primary_layer["points"]) if primary_layer else []
    regime_tags_by_bar: list[dict[str, Any]] = []
    for i, b in enumerate(bars):
        tags = regime_tags_v1_from_bar(
            b,
            vol_low_below=rp["vol_low_below"],
            vol_mid_below=rp["vol_mid_below"],
            flat_abs_pct=rp["flat_abs_pct"],
            gate_state=None,
        )
        regime_tags_by_bar.append(
            {
                "bar_index": i,
                "market_event_id": str(b.get("market_event_id") or ""),
                "regime_tags_v1": tags,
            }
        )

    mid_index = {str(b.get("market_event_id") or "").strip(): i for i, b in enumerate(bars) if b.get("market_event_id")}
    ev_idx = mid_index.get(market_event_id.strip()) if market_event_id else None
    event_bar_regime_tags = None
    if ev_idx is not None and 0 <= ev_idx < n:
        gs = _event_gate_state(trades_enriched, market_event_id.strip())
        event_bar_regime_tags = regime_tags_v1_from_bar(
            bars[ev_idx],
            vol_low_below=rp["vol_low_below"],
            vol_mid_below=rp["vol_mid_below"],
            flat_abs_pct=rp["flat_abs_pct"],
            gate_state=gs,
        )

    trade_trend_alignments: list[dict[str, Any]] = []
    for row in trades_enriched:
        et = _parse_iso(str(row.get("entry_time") or ""))
        if et is None:
            continue
        bi = _bar_index_for_time(et, bars)
        if bi is None or bi < 0 or bi >= len(regime_tags_by_bar):
            continue
        tb = (regime_tags_by_bar[bi].get("regime_tags_v1") or {}).get("trend_bucket")
        side = row.get("side")
        al, interp = interpret_side_vs_trend(str(side) if side is not None else None, str(tb) if tb is not None else None)
        trade_trend_alignments.append(
            {
                "trade_id": str(row.get("trade_id") or ""),
                "strategy_id": str(row.get("strategy_id") or ""),
                "lane": str(row.get("lane") or ""),
                "side": str(side) if side is not None else "",
                "entry_bar_index": bi,
                "trend_at_entry": tb,
                "alignment": al,
                "interpretation": interp,
            }
        )

    return {
        "schema": SCHEMA,
        "ema_period": ema_period,
        "ema_periods": list(ema_periods),
        "ema_primary_period": PRIMARY_TREND_PERIOD,
        "alignment_rule": ALIGNMENT_RULE,
        "trend_reference_layers": trend_reference_layers,
        "trend_reference_series": trend_reference_series,
        "regime_tags_by_bar": regime_tags_by_bar,
        "event_bar_index": ev_idx,
        "event_bar_regime_tags": event_bar_regime_tags,
        "trade_trend_alignments": trade_trend_alignments,
    }
