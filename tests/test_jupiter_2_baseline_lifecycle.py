"""Jupiter_2 baseline lifecycle — pure rules (SL/TP, breakeven, monotonic trail, same-bar SL wins)."""

from __future__ import annotations

import pytest

from modules.anna_training.jupiter_2_baseline_lifecycle import (
    BaselineOpenPosition,
    apply_trailing_monotonic,
    evaluate_exit_ohlc,
    initial_sl_tp,
    open_position_from_signal,
    process_holding_bar,
)


def test_initial_sl_tp_long() -> None:
    sl, tp = initial_sl_tp(entry=100.0, atr_entry=1.0, side="long")
    assert sl == pytest.approx(100.0 - 1.6)
    assert tp == pytest.approx(100.0 + 4.0)


def test_same_bar_sl_wins_long() -> None:
    ex = evaluate_exit_ohlc(
        side="long",
        stop_loss=99.0,
        take_profit=101.0,
        open_=100.0,
        high=102.0,
        low=98.0,
        close=100.0,
    )
    assert ex is not None
    reason, fill = ex
    assert reason == "STOP_LOSS"
    assert fill == 99.0


def test_trailing_monotonic_long_never_loosens() -> None:
    prev = 96.0
    # Wide candidate below prev — must keep prev
    wide = apply_trailing_monotonic(side="long", prev_stop=prev, close=100.0, atr_t=10.0)
    assert wide == prev


def test_process_exit_stop_long() -> None:
    pos = BaselineOpenPosition(
        trade_id="t1",
        side="long",
        entry_price=100.0,
        entry_market_event_id="E0",
        entry_candle_open_utc="2026-01-01T00:00:00Z",
        atr_entry=1.0,
        stop_loss=98.4,
        take_profit=104.0,
        breakeven_applied=False,
        size=1.0,
        last_processed_market_event_id="E0",
    )
    # First holding bar: E1 — range hits stop (need ≥15 closes for ATR window)
    bar = {"open": 100.0, "high": 100.5, "low": 97.0, "close": 98.0}
    base = [100.0 + i * 0.02 for i in range(19)]
    closes = base + [98.0]
    highs = [c + 0.3 for c in closes[:-1]] + [100.5]
    lows = [c - 0.3 for c in closes[:-1]] + [97.0]
    np, ex = process_holding_bar(
        pos,
        market_event_id="E1",
        closes=closes,
        highs=highs,
        lows=lows,
        bar=bar,
    )
    assert np is None and ex is not None
    assert ex["exit_reason"] == "STOP_LOSS"


def test_open_position_from_signal_sets_levels() -> None:
    bar = {
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "candle_open_utc": "2026-01-01T12:00:00Z",
    }
    p = open_position_from_signal(
        trade_id="tid",
        market_event_id="mid",
        bar=bar,
        side="long",
        atr_entry=1.0,
        size=1.0,
        reason_code="jupiter_2_long_signal",
        signal_features={"position_size_hint": {"leverage": 15}},
    )
    assert p.entry_price == 100.5
    assert p.entry_candle_open_utc == "2026-01-01T12:00:00Z"
    assert p.stop_loss < p.entry_price < p.take_profit
