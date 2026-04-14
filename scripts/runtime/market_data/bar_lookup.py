"""Read canonical bar identity from market_data.db (no duplicate bucket math)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _paths import default_market_data_path
from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP
from market_data.store import connect_market_db, ensure_market_schema


def jupiter3_binance_strategy_lookback() -> int:
    """
    Jupiter_3 only — closed bars to load from ``binance_strategy_bars_5m`` (default **1000**).

    Aligns with reference TS bot historical kline depth. Override with
    ``BLACKBOX_JUPITER3_BINANCE_LOOKBACK`` (clamped 45..1200).
    """
    try:
        n = int((os.environ.get("BLACKBOX_JUPITER3_BINANCE_LOOKBACK") or "1000").strip())
    except ValueError:
        n = 1000
    return max(45, min(1200, n))


def _binance_strategy_row_to_policy_bar_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """Map ``binance_strategy_bars_5m`` SELECT row to bar dict shape expected by Jupiter_3 policy."""
    keys = [
        "id",
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
        "volume_base_asset",
        "quote_volume_usdt",
        "price_source",
        "bar_schema_version",
        "computed_at",
    ]
    d = dict(zip(keys, row))
    d["tick_count"] = 0
    vb = d.get("volume_base_asset")
    try:
        d["volume_base"] = float(vb) if vb is not None else None
    except (TypeError, ValueError):
        d["volume_base"] = None
    d["strategy_bar_source"] = "binance_5m_ohlcv"
    return d


def binance_strategy_snapshot_max_age_sec() -> float:
    """
    Hot JSON snapshot (written by sync alongside SQLite) is trusted only if
    ``sync_wall_utc`` is within this age. Default 180s (aggressive 30s loop + slack).
    """
    try:
        v = float((os.environ.get("BLACKBOX_BINANCE_STRATEGY_SNAPSHOT_MAX_AGE_SEC") or "180").strip())
    except ValueError:
        v = 180.0
    return max(30.0, min(3600.0, v))


def binance_strategy_latest_snapshot_path(db_path: Path, canonical_symbol: str) -> Path:
    """Sidecar JSON next to ``market_data.db`` — same ingest pass as SQLite commit."""
    slug = canonical_symbol.replace("-", "_").replace("/", "_")
    return db_path.parent / f"binance_strategy_latest_{slug}.json"


def write_binance_strategy_latest_snapshot(
    conn: sqlite3.Connection,
    db_path: Path,
    canonical_symbol: str,
    *,
    sync_wall_utc_iso: str,
) -> None:
    """
    Best-effort: persist the latest ``binance_strategy_bars_5m`` row as JSON atomically
    so :func:`fetch_latest_bar_row_binance_strategy` can serve it without a second SQLite
    round-trip right after sync (same wall clock as the commit).
    """
    if not _has_binance_strategy_table(conn):
        return
    row = conn.execute(
        f"""
        {_BINANCE_STRATEGY_SELECT.strip()}
        WHERE canonical_symbol = ?
        ORDER BY candle_open_utc DESC, id DESC
        LIMIT 1
        """,
        (canonical_symbol,),
    ).fetchone()
    if not row:
        return
    path = binance_strategy_latest_snapshot_path(db_path, canonical_symbol)
    payload = {
        "canonical_symbol": canonical_symbol,
        "sync_wall_utc": sync_wall_utc_iso,
        "row": list(row),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _parse_sync_wall_utc_iso(s: str) -> datetime | None:
    t = (s or "").strip()
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _try_read_fresh_binance_strategy_snapshot(
    db_path: Path,
    canonical_symbol: str,
) -> dict[str, Any] | None:
    path = binance_strategy_latest_snapshot_path(db_path, canonical_symbol)
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("canonical_symbol") != canonical_symbol:
        return None
    sync_wall = data.get("sync_wall_utc")
    sw = _parse_sync_wall_utc_iso(str(sync_wall) if sync_wall is not None else "")
    if sw is None:
        return None
    age = (datetime.now(timezone.utc) - sw).total_seconds()
    if age < 0 or age > binance_strategy_snapshot_max_age_sec():
        return None
    row = data.get("row")
    if not isinstance(row, list) or len(row) != 15:
        return None
    return _binance_strategy_row_to_policy_bar_dict(tuple(row))


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


def fetch_recent_bars_asc(
    *,
    limit: int,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
) -> list[dict[str, Any]]:
    """
    Last ``limit`` closed bars, **oldest first** (for indicators / Sean baseline signal).

    Uses ``candle_open_utc DESC`` then reverses.
    """
    lim = max(1, int(limit))
    p = db_path or default_market_data_path()
    if not p.is_file():
        return []
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars_5m'"
        )
        if cur.fetchone() is None:
            return []
        rows = conn.execute(
            """
            SELECT id, canonical_symbol, timeframe, candle_open_utc, candle_close_utc,
                   market_event_id, open, high, low, close, tick_count, price_source, computed_at
            FROM market_bars_5m
            WHERE canonical_symbol = ?
            ORDER BY candle_open_utc DESC, id DESC
            LIMIT ?
            """,
            (canonical_symbol, lim),
        ).fetchall()
        if not rows:
            return []
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
        out = [dict(zip(keys, row)) for row in reversed(rows)]
        return out
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


def fetch_bars_asc_through_market_event_id(
    market_event_id: str,
    *,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
    max_lookback: int = 600,
) -> list[dict[str, Any]]:
    """
    Closed bars **oldest first**, ending at the bar identified by ``market_event_id`` (inclusive).

    Used when the last-N-bars window (e.g. 280) does not include an older ``market_event_id`` still
    present on the trade-chain axis — avoids ``bar_not_in_window_or_short_history`` for valid ids.
    """
    mid = (market_event_id or "").strip()
    if not mid:
        return []
    target = fetch_bar_by_market_event_id(
        mid, db_path=db_path, canonical_symbol=canonical_symbol
    )
    if not target:
        return []
    co = target.get("candle_open_utc")
    if co is None:
        return []
    lim = max(1, int(max_lookback))
    p = db_path or default_market_data_path()
    if not p.is_file():
        return []
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars_5m'"
        )
        if cur.fetchone() is None:
            return []
        rows = conn.execute(
            """
            SELECT id, canonical_symbol, timeframe, candle_open_utc, candle_close_utc,
                   market_event_id, open, high, low, close, tick_count, price_source, computed_at
            FROM market_bars_5m
            WHERE canonical_symbol = ? AND candle_open_utc <= ?
            ORDER BY candle_open_utc DESC, id DESC
            LIMIT ?
            """,
            (canonical_symbol, co, lim),
        ).fetchall()
        if not rows:
            return []
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
        rev = [dict(zip(keys, row)) for row in rows]
        return list(reversed(rev))
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


_BINANCE_STRATEGY_SELECT = """
SELECT id, canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
       market_event_id, open, high, low, close, volume_base_asset, quote_volume_usdt,
       price_source, bar_schema_version, computed_at
FROM binance_strategy_bars_5m
"""


def _has_binance_strategy_table(conn: sqlite3.Connection) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='binance_strategy_bars_5m'"
    )
    return cur.fetchone() is not None


def fetch_latest_market_event_id_binance_strategy(
    *,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
) -> str | None:
    """Latest ``market_event_id`` in ``binance_strategy_bars_5m`` (Jupiter_3 path), or None."""
    p = db_path or default_market_data_path()
    if not p.is_file():
        return None
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        ensure_market_schema(conn)
        if not _has_binance_strategy_table(conn):
            return None
        row = conn.execute(
            f"""
            {_BINANCE_STRATEGY_SELECT.strip()}
            WHERE canonical_symbol = ?
            ORDER BY candle_open_utc DESC, id DESC
            LIMIT 1
            """,
            (canonical_symbol,),
        ).fetchone()
        return str(row[6]) if row and row[6] else None
    finally:
        conn.close()


def fetch_latest_bar_row_binance_strategy(
    *,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
) -> dict[str, Any] | None:
    """
    Latest Jupiter_3 Binance strategy bar as dict (read-only), or None.

    Prefers a fresh sidecar JSON snapshot (written in the same ingest pass as SQLite) so
    the dashboard path avoids an extra SQLite read right after sync.

    **Does not read** ``market_bars_5m`` — V2 path unchanged.
    """
    p = db_path or default_market_data_path()
    if not p.is_file():
        return None
    snap = _try_read_fresh_binance_strategy_snapshot(p, canonical_symbol)
    if snap is not None:
        return snap
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout=8000")
    try:
        ensure_market_schema(conn)
        if not _has_binance_strategy_table(conn):
            return None
        row = conn.execute(
            f"""
            {_BINANCE_STRATEGY_SELECT.strip()}
            WHERE canonical_symbol = ?
            ORDER BY candle_open_utc DESC, id DESC
            LIMIT 1
            """,
            (canonical_symbol,),
        ).fetchone()
        if not row:
            return None
        return _binance_strategy_row_to_policy_bar_dict(row)
    finally:
        conn.close()


def fetch_recent_bars_asc_binance_strategy(
    *,
    limit: int | None = None,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
) -> list[dict[str, Any]]:
    """
    Last ``limit`` closed Binance strategy bars, **oldest first** (Jupiter_3 only).

    Default ``limit`` is :func:`jupiter3_binance_strategy_lookback` (1000).
    """
    lim = jupiter3_binance_strategy_lookback() if limit is None else max(1, int(limit))
    p = db_path or default_market_data_path()
    if not p.is_file():
        return []
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        ensure_market_schema(conn)
        if not _has_binance_strategy_table(conn):
            return []
        rows = conn.execute(
            f"""
            {_BINANCE_STRATEGY_SELECT.strip()}
            WHERE canonical_symbol = ?
            ORDER BY candle_open_utc DESC, id DESC
            LIMIT ?
            """,
            (canonical_symbol, lim),
        ).fetchall()
        if not rows:
            return []
        out = [_binance_strategy_row_to_policy_bar_dict(row) for row in reversed(rows)]
        return out
    finally:
        conn.close()


def fetch_bars_asc_through_market_event_id_binance_strategy(
    market_event_id: str,
    *,
    db_path: Path | None = None,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
    max_lookback: int | None = None,
) -> list[dict[str, Any]]:
    """
    Closed Binance strategy bars **oldest first**, ending at ``market_event_id`` (inclusive).

    ``max_lookback`` defaults to :func:`jupiter3_binance_strategy_lookback`.
    """
    mid = (market_event_id or "").strip()
    if not mid:
        return []
    lb = jupiter3_binance_strategy_lookback() if max_lookback is None else max(1, int(max_lookback))
    p = db_path or default_market_data_path()
    if not p.is_file():
        return []
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        ensure_market_schema(conn)
        if not _has_binance_strategy_table(conn):
            return []
        target = conn.execute(
            f"""
            {_BINANCE_STRATEGY_SELECT.strip()}
            WHERE market_event_id = ? AND canonical_symbol = ?
            LIMIT 1
            """,
            (mid, canonical_symbol),
        ).fetchone()
        if not target:
            return []
        co = target[4]
        rows = conn.execute(
            f"""
            {_BINANCE_STRATEGY_SELECT.strip()}
            WHERE canonical_symbol = ? AND candle_open_utc <= ?
            ORDER BY candle_open_utc DESC, id DESC
            LIMIT ?
            """,
            (canonical_symbol, co, lb),
        ).fetchall()
        if not rows:
            return []
        rev = [_binance_strategy_row_to_policy_bar_dict(row) for row in rows]
        return list(reversed(rev))
    finally:
        conn.close()
