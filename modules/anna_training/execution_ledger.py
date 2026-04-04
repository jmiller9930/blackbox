"""SQLite execution ledger — parallel trades with full identity (strategy_id, lane, mode, market_event_id)."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from modules.anna_training.store import utc_now_iso

RESERVED_STRATEGY_BASELINE = "baseline"
VALID_LANES = frozenset({"baseline", "anna"})
VALID_MODES = frozenset({"live", "paper"})
SCHEMA_VERSION = "execution_trade_v1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_execution_ledger_path() -> Path:
    env = os.environ.get("BLACKBOX_EXECUTION_LEDGER_PATH")
    if env:
        return Path(env).expanduser()
    return _repo_root() / "data" / "sqlite" / "execution_ledger.db"


def _strict_trade_identity() -> bool:
    return (os.environ.get("ANNA_STRICT_TRADE_IDENTITY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def connect_ledger(db_path: Path | None = None) -> sqlite3.Connection:
    p = db_path or default_execution_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(p)


def ensure_execution_ledger_schema(conn: sqlite3.Connection, root: Path | None = None) -> None:
    root = root or _repo_root()
    sql = root / "data" / "sqlite" / "schema_execution_ledger.sql"
    if not sql.is_file():
        raise FileNotFoundError(sql)
    conn.executescript(sql.read_text(encoding="utf-8"))
    conn.commit()


def _validate_lane_strategy(lane: str, strategy_id: str) -> None:
    lane = (lane or "").strip().lower()
    sid = (strategy_id or "").strip()
    if lane not in VALID_LANES:
        raise ValueError(f"lane must be one of {sorted(VALID_LANES)}")
    if lane == "baseline" and sid != RESERVED_STRATEGY_BASELINE:
        raise ValueError("lane=baseline requires strategy_id=baseline")
    if lane == "anna" and sid == RESERVED_STRATEGY_BASELINE:
        raise ValueError("strategy_id baseline is reserved for lane=baseline only")


def append_execution_trade(
    *,
    strategy_id: str,
    lane: str,
    mode: str,
    market_event_id: str,
    symbol: str,
    timeframe: str,
    trade_id: str | None = None,
    side: str | None = None,
    entry_time: str | None = None,
    entry_price: float | None = None,
    size: float | None = None,
    exit_time: str | None = None,
    exit_price: float | None = None,
    exit_reason: str | None = None,
    pnl_usd: float | None = None,
    context_snapshot: dict[str, Any] | None = None,
    notes: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """
    Persist one trade row. ``trade_id`` defaults to UUID.

    When ``ANNA_STRICT_TRADE_IDENTITY=1``, requires non-empty market_event_id, symbol, timeframe,
    and entry/exit fields (minimal paper stubs must still supply placeholders).
    """
    _validate_lane_strategy(lane, strategy_id)
    mode = (mode or "").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
    if lane == "anna" and mode == "live":
        raise ValueError("Anna lane is paper-only until policy changes")
    mid = (market_event_id or "").strip()
    if not mid:
        raise ValueError("market_event_id is required")
    sym = (symbol or "").strip()
    tf = (timeframe or "").strip()
    if _strict_trade_identity():
        for name, val in (
            ("symbol", sym),
            ("timeframe", tf),
            ("entry_time", entry_time),
            ("exit_time", exit_time),
            ("exit_reason", exit_reason),
        ):
            if not val:
                raise ValueError(f"ANNA_STRICT_TRADE_IDENTITY: {name} required")
        if entry_price is None or exit_price is None or pnl_usd is None:
            raise ValueError("ANNA_STRICT_TRADE_IDENTITY: entry_price, exit_price, pnl_usd required")

    tid = (trade_id or "").strip() or str(uuid.uuid4())
    ctx_json = json.dumps(context_snapshot, ensure_ascii=False) if context_snapshot else None

    created = utc_now_iso()
    row = {
        "trade_id": tid,
        "strategy_id": strategy_id.strip(),
        "lane": lane.strip().lower(),
        "mode": mode,
        "market_event_id": mid,
        "symbol": sym,
        "timeframe": tf,
        "side": (side or "").strip().lower() or None,
        "entry_time": entry_time,
        "entry_price": entry_price,
        "size": size,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": (exit_reason or "").strip() or None,
        "pnl_usd": pnl_usd,
        "context_snapshot_json": ctx_json,
        "notes": (notes or "").strip() or None,
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": created,
    }

    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        conn.execute(
            """
            INSERT INTO execution_trades (
              trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
              side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
              pnl_usd, context_snapshot_json, notes, schema_version, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["trade_id"],
                row["strategy_id"],
                row["lane"],
                row["mode"],
                row["market_event_id"],
                row["symbol"],
                row["timeframe"],
                row["side"],
                row["entry_time"],
                row["entry_price"],
                row["size"],
                row["exit_time"],
                row["exit_price"],
                row["exit_reason"],
                row["pnl_usd"],
                row["context_snapshot_json"],
                row["notes"],
                row["schema_version"],
                row["created_at_utc"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return row


def query_trades_by_market_event_id(
    market_event_id: str,
    *,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, schema_version, created_at_utc
            FROM execution_trades
            WHERE market_event_id = ?
            ORDER BY created_at_utc ASC, trade_id ASC
            """,
            (market_event_id.strip(),),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def query_trades_by_strategy(
    strategy_id: str,
    *,
    limit: int = 500,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, schema_version, created_at_utc
            FROM execution_trades
            WHERE strategy_id = ?
            ORDER BY created_at_utc DESC, trade_id DESC
            LIMIT ?
            """,
            (strategy_id.strip(), int(limit)),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def sync_strategy_registry_from_catalog(conn: sqlite3.Connection) -> int:
    """Upsert rows from ``strategy_catalog`` + reserved baseline. Returns count written."""
    from modules.anna_training.strategy_catalog import load_strategy_catalog

    now = utc_now_iso()
    n = 0
    rows = list(load_strategy_catalog())
    rows.append(
        {
            "id": RESERVED_STRATEGY_BASELINE,
            "title": "Sean baseline (reserved)",
            "description": "Baseline execution mechanics; lane=baseline only.",
        }
    )
    for s in rows:
        sid = str(s.get("id") or "").strip()
        if not sid:
            continue
        conn.execute(
            """
            INSERT INTO strategy_registry (strategy_id, title, description, registered_at_utc, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(strategy_id) DO UPDATE SET
              title = excluded.title,
              description = excluded.description
            """,
            (
                sid,
                str(s.get("title") or "")[:500],
                str(s.get("description") or "")[:2000],
                now,
                "catalog" if sid != RESERVED_STRATEGY_BASELINE else "reserved",
            ),
        )
        n += 1
    conn.commit()
    return n
