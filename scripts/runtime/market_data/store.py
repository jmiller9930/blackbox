"""SQLite market_data.db — canonical tick storage (Phase 5.1)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _paths import repo_root

from market_data.canonical_bar import CanonicalBarV1
from market_data.canonical_time import (
    candle_close_utc_exclusive,
    format_candle_open_iso_z,
)


def connect_market_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def _migrate_market_ticks_tertiary(conn: sqlite3.Connection) -> None:
    """Add Jupiter/tertiary columns to older DBs created before optional tertiary leg."""
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_ticks'")
    if cur.fetchone() is None:
        return
    info = conn.execute("PRAGMA table_info(market_ticks)").fetchall()
    cols = {row[1] for row in info}
    alters: list[str] = []
    if "tertiary_source" not in cols:
        alters.append("ALTER TABLE market_ticks ADD COLUMN tertiary_source TEXT")
    if "tertiary_price" not in cols:
        alters.append("ALTER TABLE market_ticks ADD COLUMN tertiary_price REAL")
    if "tertiary_observed_at" not in cols:
        alters.append("ALTER TABLE market_ticks ADD COLUMN tertiary_observed_at TEXT")
    if "tertiary_raw_json" not in cols:
        alters.append("ALTER TABLE market_ticks ADD COLUMN tertiary_raw_json TEXT")
    for sql in alters:
        conn.execute(sql)


def ensure_market_schema(conn: sqlite3.Connection, root: Path | None = None) -> None:
    root = root or repo_root()
    p = root / "data" / "sqlite" / "schema_phase5_market_data.sql"
    if not p.is_file():
        raise FileNotFoundError(p)
    conn.executescript(p.read_text(encoding="utf-8"))
    _migrate_market_ticks_tertiary(conn)
    p2 = root / "data" / "sqlite" / "schema_phase5_canonical_bars.sql"
    if p2.is_file():
        conn.executescript(p2.read_text(encoding="utf-8"))
    conn.commit()


def insert_tick(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    inserted_at: str,
    primary_source: str,
    primary_price: float | None,
    primary_observed_at: str | None,
    primary_publish_time: int | None,
    primary_raw: dict[str, Any] | None,
    comparator_source: str,
    comparator_price: float | None,
    comparator_observed_at: str | None,
    comparator_raw: dict[str, Any] | None,
    gate_state: str,
    gate_reason: str,
    tertiary_source: str | None = None,
    tertiary_price: float | None = None,
    tertiary_observed_at: str | None = None,
    tertiary_raw: dict[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO market_ticks (
          symbol, inserted_at,
          primary_source, primary_price, primary_observed_at, primary_publish_time, primary_raw_json,
          comparator_source, comparator_price, comparator_observed_at, comparator_raw_json,
          tertiary_source, tertiary_price, tertiary_observed_at, tertiary_raw_json,
          gate_state, gate_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            inserted_at,
            primary_source,
            primary_price,
            primary_observed_at,
            primary_publish_time,
            json.dumps(primary_raw, ensure_ascii=False) if primary_raw is not None else None,
            comparator_source,
            comparator_price,
            comparator_observed_at,
            json.dumps(comparator_raw, ensure_ascii=False) if comparator_raw is not None else None,
            tertiary_source,
            tertiary_price,
            tertiary_observed_at,
            json.dumps(tertiary_raw, ensure_ascii=False) if tertiary_raw is not None else None,
            gate_state,
            gate_reason,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def latest_row_primary_leg(conn: sqlite3.Connection, symbol: str) -> dict[str, Any] | None:
    """Latest stored primary (oracle) leg for ``symbol`` — replay Pyth from SQLite without network I/O."""
    row = conn.execute(
        """
        SELECT primary_source, primary_price, primary_observed_at, primary_publish_time, primary_raw_json
        FROM market_ticks
        WHERE symbol = ?
        ORDER BY inserted_at DESC, id DESC
        LIMIT 1
        """,
        (symbol,),
    ).fetchone()
    if row is None:
        return None
    keys = (
        "primary_source",
        "primary_price",
        "primary_observed_at",
        "primary_publish_time",
        "primary_raw_json",
    )
    return dict(zip(keys, row))


def latest_tick(conn: sqlite3.Connection, symbol: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, symbol, inserted_at, primary_source, primary_price, primary_observed_at,
               comparator_source, comparator_price, comparator_observed_at,
               tertiary_source, tertiary_price, tertiary_observed_at,
               gate_state, gate_reason
        FROM market_ticks
        WHERE symbol = ?
        ORDER BY inserted_at DESC, id DESC
        LIMIT 1
        """,
        (symbol,),
    ).fetchone()
    if row is None:
        return None
    cols = [
        "id",
        "symbol",
        "inserted_at",
        "primary_source",
        "primary_price",
        "primary_observed_at",
        "comparator_source",
        "comparator_price",
        "comparator_observed_at",
        "tertiary_source",
        "tertiary_price",
        "tertiary_observed_at",
        "gate_state",
        "gate_reason",
    ]
    return dict(zip(cols, row))


def ticks_chronological(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return stored ticks for ``symbol`` oldest-first (deterministic order for simulation).

    Read-only consumer should use a readonly connection.  Same row shape as
    :func:`latest_tick`.
    """

    cols = [
        "id",
        "symbol",
        "inserted_at",
        "primary_source",
        "primary_price",
        "primary_observed_at",
        "comparator_source",
        "comparator_price",
        "comparator_observed_at",
        "tertiary_source",
        "tertiary_price",
        "tertiary_observed_at",
        "gate_state",
        "gate_reason",
    ]
    sql = f"""
        SELECT {", ".join(cols)}
        FROM market_ticks
        WHERE symbol = ?
        ORDER BY inserted_at ASC, id ASC
    """
    params: list[Any] = [symbol]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(zip(cols, row)) for row in rows]


def ticks_in_bucket_5m(
    conn: sqlite3.Connection,
    tick_symbol: str,
    candle_open_utc: datetime,
) -> list[dict[str, Any]]:
    """Ticks with ``inserted_at`` in ``[candle_open, candle_close)`` (exclusive end)."""
    o = format_candle_open_iso_z(candle_open_utc)
    c = format_candle_open_iso_z(candle_close_utc_exclusive(candle_open_utc))
    cols = [
        "id",
        "symbol",
        "inserted_at",
        "primary_source",
        "primary_price",
        "primary_observed_at",
        "comparator_source",
        "comparator_price",
        "comparator_observed_at",
        "tertiary_source",
        "tertiary_price",
        "tertiary_observed_at",
        "gate_state",
        "gate_reason",
    ]
    sql = f"""
        SELECT {", ".join(cols)}
        FROM market_ticks
        WHERE symbol = ? AND inserted_at >= ? AND inserted_at < ?
        ORDER BY inserted_at ASC, id ASC
    """
    rows = conn.execute(sql, (tick_symbol, o, c)).fetchall()
    return [dict(zip(cols, row)) for row in rows]


def upsert_market_bar_5m(conn: sqlite3.Connection, bar: CanonicalBarV1) -> None:
    """Insert or replace one canonical 5m bar by ``market_event_id``."""
    computed = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = bar.to_row_dict()
    conn.execute(
        """
        INSERT INTO market_bars_5m (
          canonical_symbol, tick_symbol, timeframe,
          candle_open_utc, candle_close_utc, market_event_id,
          open, high, low, close, tick_count, volume_base,
          price_source, bar_schema_version, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(market_event_id) DO UPDATE SET
          open = excluded.open,
          high = excluded.high,
          low = excluded.low,
          close = excluded.close,
          tick_count = excluded.tick_count,
          volume_base = excluded.volume_base,
          price_source = excluded.price_source,
          bar_schema_version = excluded.bar_schema_version,
          computed_at = excluded.computed_at
        """,
        (
            r["canonical_symbol"],
            r["tick_symbol"],
            r["timeframe"],
            r["candle_open_utc"],
            r["candle_close_utc"],
            r["market_event_id"],
            r["open"],
            r["high"],
            r["low"],
            r["close"],
            r["tick_count"],
            r["volume_base"],
            r["price_source"],
            r["bar_schema_version"],
            computed,
        ),
    )
    conn.commit()


def fetch_bar_by_market_event_id(conn: sqlite3.Connection, market_event_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
               market_event_id, open, high, low, close, tick_count, volume_base,
               price_source, bar_schema_version, computed_at
        FROM market_bars_5m
        WHERE market_event_id = ?
        """,
        (market_event_id,),
    ).fetchone()
    if row is None:
        return None
    keys = [
        "canonical_symbol",
        "tick_symbol",
        "timeframe",
        "candle_open_utc",
        "candle_close_utc",
        "market_event_id",
        "open",
        "high",
        "low",
        "close",
        "tick_count",
        "volume_base",
        "price_source",
        "bar_schema_version",
        "computed_at",
    ]
    return dict(zip(keys, row))


def latest_stored_bars(
    conn: sqlite3.Connection,
    canonical_symbol: str,
    *,
    limit: int = 32,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
               market_event_id, open, high, low, close, tick_count, volume_base,
               price_source, bar_schema_version, computed_at
        FROM market_bars_5m
        WHERE canonical_symbol = ?
        ORDER BY candle_open_utc DESC, id DESC
        LIMIT ?
        """,
        (canonical_symbol, int(limit)),
    ).fetchall()
    keys = [
        "canonical_symbol",
        "tick_symbol",
        "timeframe",
        "candle_open_utc",
        "candle_close_utc",
        "market_event_id",
        "open",
        "high",
        "low",
        "close",
        "tick_count",
        "volume_base",
        "price_source",
        "bar_schema_version",
        "computed_at",
    ]
    return [dict(zip(keys, row)) for row in rows]
