"""Single canonical instrument identity for market_event_id and bars (aligns with Sean baseline SOL-PERP)."""

from __future__ import annotations

# Tick recorder / Pyth logical symbol (existing market_ticks.symbol)
TICK_SYMBOL_SOL_DEFAULT = "SOL-USD"

# Canonical perp instrument id — same market object as trading_core Drift path (SOL-PERP).
CANONICAL_INSTRUMENT_SOL_PERP = "SOL-PERP"

TIMEFRAME_5M = "5m"


def canonical_symbol_for_tick_symbol(tick_symbol: str) -> str:
    """Map recorder tick symbol to the one canonical id used in market_event_id."""
    t = (tick_symbol or "").strip()
    if t in (TICK_SYMBOL_SOL_DEFAULT, "SOL-USD"):
        return CANONICAL_INSTRUMENT_SOL_PERP
    return t
