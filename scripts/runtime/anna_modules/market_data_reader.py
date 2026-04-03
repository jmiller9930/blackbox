"""Read latest row from shared `market_data.db` for Anna analysis (Phase 5.1)."""

from __future__ import annotations

import sqlite3
from typing import Any

from _paths import default_market_data_path
from market_data.store import latest_tick

DEFAULT_SYMBOL = "SOL-USD"


def load_latest_market_tick(symbol: str = DEFAULT_SYMBOL) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(tick, err)``. ``err`` is None when a row exists; otherwise a short reason."""
    p = default_market_data_path()
    if not p.is_file():
        return None, "market_data_db_missing"
    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            t = latest_tick(conn, symbol)
        finally:
            conn.close()
    except OSError as exc:
        return None, str(exc)
    if t is None:
        return None, "no_tick_for_symbol"
    return t, None
