"""SQLite market_data.db — canonical tick storage (Phase 5.1)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from _paths import repo_root


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
