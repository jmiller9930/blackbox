"""Sean baseline signal — parity with trading_core aggregateCandles + rsi."""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bar(i: int, *, o: float, h: float, l: float, c: float) -> dict:
    return {
        "id": i,
        "canonical_symbol": "SOL-PERP",
        "timeframe": "5m",
        "candle_open_utc": f"2026-01-01T00:{i:03d}:00Z",
        "candle_close_utc": f"2026-01-01T00:{i:03d}:05Z",
        "market_event_id": f"SOL-PERP_5m_test_{i:04d}",
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "tick_count": 3,
        "price_source": "test",
        "computed_at": "2026-01-01T00:00:00Z",
    }


def test_insufficient_history() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import MIN_BARS, evaluate_sean_jupiter_baseline_v1

    bars = [_bar(i, o=100.0, h=101.0, l=99.0, c=100.0) for i in range(MIN_BARS - 1)]
    out = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    assert out.trade is False
    assert out.reason_code == "insufficient_history"


def test_aggregate_candles_flags_short_parity() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import aggregate_candles_signal_flags

    prev_c = {"high": 100.0, "low": 99.0}
    curr_c = {"high": 100.5, "low": 99.0}
    short, long_ = aggregate_candles_signal_flags(
        prev_candle=prev_c,
        curr_candle=curr_c,
        prev_rsi_raw=65.0,
        current_rsi_raw=62.0,
    )
    assert short is True
    assert long_ is False


def test_aggregate_candles_flags_long_parity() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import aggregate_candles_signal_flags

    prev_c = {"high": 101.0, "low": 100.0}
    curr_c = {"high": 100.5, "low": 98.5}
    short, long_ = aggregate_candles_signal_flags(
        prev_candle=prev_c,
        curr_candle=curr_c,
        prev_rsi_raw=38.0,
        current_rsi_raw=39.0,
    )
    assert short is False
    assert long_ is True


def test_flat_closes_often_no_signal() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import MIN_BARS, evaluate_sean_jupiter_baseline_v1

    bars = [_bar(i, o=100.0, h=100.0, l=100.0, c=100.0) for i in range(MIN_BARS + 5)]
    out = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    assert out.trade is False
    assert out.reason_code == "no_signal"


def test_rsi_trading_core_length_matches_ts() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import RSI_PERIOD, rsi_trading_core

    closes = [100.0 + i * 0.1 for i in range(30)]
    r = rsi_trading_core(closes)
    assert len(r) == len(closes)
    assert math.isnan(r[RSI_PERIOD - 1])
    assert not math.isnan(r[RSI_PERIOD])
