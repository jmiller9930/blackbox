"""Recompute and persist the last closed 5m bar from ticks (call after each tick ingest)."""

from __future__ import annotations

from typing import Any

from market_data.canonical_bar import build_canonical_bar_from_ticks
from market_data.canonical_instrument import TIMEFRAME_5M, canonical_symbol_for_tick_symbol
from market_data.canonical_time import format_candle_open_iso_z, last_closed_candle_open_utc
from market_data.store import ticks_in_bucket_5m, upsert_market_bar_5m


def refresh_last_closed_bar_from_ticks(conn: Any, tick_symbol: str) -> dict[str, Any]:
    """
    Aggregate ticks for the **last closed** 5m bucket and upsert ``market_bars_5m``.

    Returns a small status dict for logging / tests.
    """
    canonical = canonical_symbol_for_tick_symbol(tick_symbol)
    last_open = last_closed_candle_open_utc()
    ticks = ticks_in_bucket_5m(conn, tick_symbol, last_open)
    bar = build_canonical_bar_from_ticks(
        ticks=ticks,
        tick_symbol=tick_symbol,
        canonical_symbol=canonical,
        candle_open_utc=last_open,
        timeframe=TIMEFRAME_5M,
    )
    if bar is None:
        return {
            "ok": False,
            "reason": "no_ticks_in_closed_bucket",
            "tick_symbol": tick_symbol,
            "canonical_symbol": canonical,
            "candle_open_utc": format_candle_open_iso_z(last_open),
            "tick_count": len(ticks),
        }
    upsert_market_bar_5m(conn, bar)
    return {
        "ok": True,
        "market_event_id": bar.market_event_id,
        "canonical_symbol": canonical,
        "candle_open_utc": format_candle_open_iso_z(last_open),
        "tick_count": bar.tick_count,
    }
