"""
market_state_builder.py

Purpose:
Build a MarketState object from a rolling historical bar window.

Usage:
Used by the replay runner before feature generation.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.market_state import MarketState

WINDOW_SIZE = 50


def build_market_state(rows: list) -> MarketState:
    """
    Build and return a MarketState from a list of SQLite rows.
    The final row in the list is treated as the current bar.
    """
    if not rows:
        raise ValueError("[market_state_builder] No rows provided")

    window = rows[-WINDOW_SIZE:]
    current_row = window[-1]

    closes = [float(row["close"]) for row in window]
    highs = [float(row["high"]) for row in window]
    lows = [float(row["low"]) for row in window]
    opens = [float(row["open"]) for row in window]
    volumes = [float(row["volume"]) for row in window]

    state = MarketState(
        symbol=current_row["symbol"],
        timestamp=int(current_row["open_time"]),
        closes=closes,
        highs=highs,
        lows=lows,
        opens=opens,
        volumes=volumes,
        current_open=float(current_row["open"]),
        current_high=float(current_row["high"]),
        current_low=float(current_row["low"]),
        current_close=float(current_row["close"]),
        current_volume=float(current_row["volume"]),
    )

    print(
        "[market_state_builder] Built MarketState "
        f"symbol={state.symbol} timestamp={state.timestamp} close={state.current_close}"
    )

    return state
