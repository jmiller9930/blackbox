"""Read canonical bar identity from market_data.db (no duplicate bucket math)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from _paths import default_market_data_path
from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP
from market_data.store import connect_market_db, ensure_market_schema


def fetch_latest_market_event_id(
    *,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
) -> str | None:
    """Return ``market_event_id`` of the most recently stored closed 5m bar, if any."""
    p = db_path or default_market_data_path()
    if not p.is_file():
        return None
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            """
            SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars_5m'
            """
        )
        if cur.fetchone() is None:
            return None
        row = conn.execute(
            """
            SELECT market_event_id FROM market_bars_5m
            WHERE canonical_symbol = ?
            ORDER BY candle_open_utc DESC, id DESC
            LIMIT 1
            """,
            (canonical_symbol,),
        ).fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        conn.close()


def fetch_latest_bar_row(
    *,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
) -> dict[str, Any] | None:
    """Latest canonical bar as dict (read-only), or None."""
    p = db_path or default_market_data_path()
    if not p.is_file():
        return None
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars_5m'"
        )
        if cur.fetchone() is None:
            return None
        row = conn.execute(
            """
            SELECT id, canonical_symbol, timeframe, candle_open_utc, candle_close_utc,
                   market_event_id, open, high, low, close, tick_count, price_source, computed_at
            FROM market_bars_5m
            WHERE canonical_symbol = ?
            ORDER BY candle_open_utc DESC, id DESC
            LIMIT 1
            """,
            (canonical_symbol,),
        ).fetchone()
        if not row:
            return None
        keys = [
            "id",
            "canonical_symbol",
            "timeframe",
            "candle_open_utc",
            "candle_close_utc",
            "market_event_id",
            "open",
            "high",
            "low",
            "close",
            "tick_count",
            "price_source",
            "computed_at",
        ]
        return dict(zip(keys, row))
    finally:
        conn.close()


def fetch_bar_by_market_event_id(
    market_event_id: str,
    *,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
) -> dict[str, Any] | None:
    """Return one canonical bar row for ``market_event_id``, or None."""
    mid = (market_event_id or "").strip()
    if not mid:
        return None
    p = db_path or default_market_data_path()
    if not p.is_file():
        return None
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars_5m'"
        )
        if cur.fetchone() is None:
            return None
        row = conn.execute(
            """
            SELECT id, canonical_symbol, timeframe, candle_open_utc, candle_close_utc,
                   market_event_id, open, high, low, close, tick_count, price_source, computed_at
            FROM market_bars_5m
            WHERE market_event_id = ? AND canonical_symbol = ?
            LIMIT 1
            """,
            (mid, canonical_symbol),
        ).fetchone()
        if not row:
            return None
        keys = [
            "id",
            "canonical_symbol",
            "timeframe",
            "candle_open_utc",
            "candle_close_utc",
            "market_event_id",
            "open",
            "high",
            "low",
            "close",
            "tick_count",
            "price_source",
            "computed_at",
        ]
        return dict(zip(keys, row))
    finally:
        conn.close()


def ensure_market_db_has_bar_table(db_path: Path | None = None) -> bool:
    """True if ``market_bars_5m`` exists (schema applied)."""
    p = db_path or default_market_data_path()
    if not p.is_file():
        return False
    conn = connect_market_db(p)
    try:
        ensure_market_schema(conn)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars_5m'"
        )
        return cur.fetchone() is not None
    finally:
        conn.close()
