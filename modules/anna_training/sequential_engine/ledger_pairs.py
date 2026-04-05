"""Load baseline + Anna execution_ledger rows for one market_event_id."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    connect_ledger,
    default_execution_ledger_path,
    ensure_execution_ledger_schema,
)


def count_paired_market_events(
    *,
    candidate_strategy_id: str,
    db_path: Path | None = None,
) -> int:
    """Count distinct ``market_event_id`` with both baseline and anna rows for ``candidate_strategy_id``."""
    sid = (candidate_strategy_id or "").strip()
    if not sid:
        return 0
    conn = connect_ledger(db_path or default_execution_ledger_path())
    try:
        ensure_execution_ledger_schema(conn)
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT a.market_event_id)
            FROM execution_trades a
            INNER JOIN execution_trades b ON a.market_event_id = b.market_event_id
            WHERE a.lane = 'anna' AND a.strategy_id = ?
              AND b.lane = 'baseline' AND b.strategy_id = ?
            """,
            (sid, RESERVED_STRATEGY_BASELINE),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


def _row_to_dict(cur: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    raw = d.get("context_snapshot_json")
    if raw:
        try:
            d["context_snapshot"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            d["context_snapshot"] = {}
    else:
        d["context_snapshot"] = {}
    return d


def fetch_paired_trades_for_event(
    market_event_id: str,
    *,
    candidate_strategy_id: str,
    db_path: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Latest baseline row (lane=baseline, strategy_id=baseline) and latest Anna row
    for ``candidate_strategy_id`` (lane=anna), same ``market_event_id``.
    """
    mid = (market_event_id or "").strip()
    sid = (candidate_strategy_id or "").strip()
    if not mid or not sid:
        return None, None

    conn = connect_ledger(db_path or default_execution_ledger_path())
    try:
        ensure_execution_ledger_schema(conn)
        cur_b = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, trace_id, created_at_utc
            FROM execution_trades
            WHERE market_event_id = ? AND lane = 'baseline' AND strategy_id = ?
            ORDER BY created_at_utc DESC, trade_id DESC
            LIMIT 1
            """,
            (mid, RESERVED_STRATEGY_BASELINE),
        )
        br = cur_b.fetchone()
        base = _row_to_dict(cur_b, br) if br else None

        cur_c = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, trace_id, created_at_utc
            FROM execution_trades
            WHERE market_event_id = ? AND lane = 'anna' AND strategy_id = ?
            ORDER BY created_at_utc DESC, trade_id DESC
            LIMIT 1
            """,
            (mid, sid),
        )
        cr = cur_c.fetchone()
        cand = _row_to_dict(cur_c, cr) if cr else None
        return base, cand
    finally:
        conn.close()
