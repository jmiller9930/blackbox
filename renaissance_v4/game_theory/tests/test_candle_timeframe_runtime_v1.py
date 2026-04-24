"""Candle rollup (trade window) from 5m base rows."""

from __future__ import annotations

from renaissance_v4.game_theory.candle_timeframe_runtime import (
    annotate_scenarios_with_candle_timeframe,
    extract_candle_timeframe_minutes_for_replay,
    resolve_ui_trade_window,
    rollup_5m_rows_to_candle_timeframe,
)


def test_resolve_ui_trade_window() -> None:
    r = resolve_ui_trade_window("4h")
    assert r["candle_timeframe_minutes"] == 240
    assert r["trade_window_mode"] == "4h"


def test_rollup_15m_three_base_bars_per_candle() -> None:
    base = 1_700_000_000
    rows = []
    for i in range(6):
        t = base + i * 300  # 5m apart
        rows.append(
            {
                "symbol": "SOLUSDT",
                "open_time": t,
                "open": 1.0 + i,
                "high": 2.0 + i,
                "low": 0.5 + i,
                "close": 1.5 + i,
                "volume": 10.0 * (i + 1),
            }
        )
    out, audit = rollup_5m_rows_to_candle_timeframe(rows, target_minutes=15)
    assert audit["rollup_applied"] is True
    assert len(out) == 2
    assert out[0]["open"] == 1.0
    assert out[0]["close"] == 3.5  # last of first group (i=2)
    assert out[0]["high"] == 4.0
    assert out[0]["low"] == 0.5
    assert out[0]["volume"] == 10.0 + 20.0 + 30.0
    assert out[1]["open"] == 4.0
    assert out[1]["close"] == 6.5


def test_extract_from_scenario_evaluation_window() -> None:
    s = {"evaluation_window": {"calendar_months": 12, "candle_timeframe_minutes": 60}}
    assert extract_candle_timeframe_minutes_for_replay(s) == 60


def test_annotate_merges_into_scenarios() -> None:
    tw = resolve_ui_trade_window("15m")
    scenarios = [{"scenario_id": "a", "evaluation_window": {"calendar_months": 12}}]
    annotate_scenarios_with_candle_timeframe(scenarios, resolved=tw)
    ew = scenarios[0]["evaluation_window"]
    assert ew["candle_timeframe_minutes"] == 15
    assert ew["candle_timeframe_ui_mode"] == "15m"
