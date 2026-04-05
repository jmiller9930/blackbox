"""Trend context — server-side alignment and EMA (no UI inference)."""

from __future__ import annotations

from modules.anna_training.quantitative_evaluation_layer.regime_tags_v1 import (
    TREND_DOWN,
    TREND_FLAT,
    TREND_UP,
)
from modules.anna_training.trend_context import (
    build_trend_context,
    ema_from_closes,
    interpret_side_vs_trend,
)


def test_interpret_long_up_with() -> None:
    al, _ = interpret_side_vs_trend("long", TREND_UP)
    assert al == "with_trend"


def test_interpret_long_down_against() -> None:
    al, _ = interpret_side_vs_trend("long", TREND_DOWN)
    assert al == "against_trend"


def test_interpret_short_down_with() -> None:
    al, _ = interpret_side_vs_trend("short", TREND_DOWN)
    assert al == "with_trend"


def test_interpret_short_up_against() -> None:
    al, _ = interpret_side_vs_trend("short", TREND_UP)
    assert al == "against_trend"


def test_interpret_flat_neutral() -> None:
    al, _ = interpret_side_vs_trend("long", TREND_FLAT)
    assert al == "neutral_trend"


def test_ema_monotonic_length() -> None:
    closes = [100.0, 101.0, 100.5, 102.0]
    e = ema_from_closes(closes, 20)
    assert len(e) == 4
    assert all(x is not None for x in e)


def test_build_trend_context_minimal() -> None:
    mid = "X_5m_2026-04-01T00:00:00Z"
    bars = [
        {
            "candle_open_utc": "2026-04-01T00:00:00Z",
            "candle_close_utc": "2026-04-01T00:05:00Z",
            "open": 100.0,
            "high": 101.0,
            "low": 99.5,
            "close": 100.8,
            "market_event_id": mid,
        },
        {
            "candle_open_utc": "2026-04-01T00:05:00Z",
            "candle_close_utc": "2026-04-01T00:10:00Z",
            "open": 100.8,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "market_event_id": "other",
        },
    ]
    trades = [
        {
            "trade_id": "t1",
            "strategy_id": "s1",
            "lane": "anna",
            "side": "long",
            "entry_time": "2026-04-01T00:00:00Z",
            "market_event_id": mid,
            "context_snapshot": {},
        }
    ]
    out = build_trend_context(
        history_bars=list(reversed(bars)),
        market_event_id=mid,
        trades_enriched=trades,
    )
    assert out["schema"] == "trend_context_v1"
    assert len(out["trend_reference_series"]) >= 1
    assert out["event_bar_regime_tags"] is not None
    assert len(out["trade_trend_alignments"]) == 1
    assert out["trade_trend_alignments"][0]["alignment"] in (
        "with_trend",
        "against_trend",
        "neutral_trend",
        "unknown",
    )
