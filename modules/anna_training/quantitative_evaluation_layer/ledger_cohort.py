"""Ledger-backed cohorts for QEL — execution ledger is authoritative (not JSONL)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import (
    connect_ledger,
    default_execution_ledger_path,
    ensure_execution_ledger_schema,
    is_economic_mode,
)


def _default_market_db_path() -> Path:
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_DB") or "").strip()
    if raw:
        return Path(raw).expanduser()
    # Repo root is parents[3]: …/quantitative_evaluation_layer/ledger_cohort.py → anna_training → modules → blackbox
    return Path(__file__).resolve().parents[3] / "data" / "sqlite" / "market_data.db"


def fetch_bar_by_market_event_id(
    market_event_id: str,
    *,
    market_db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Read one canonical bar row by market_event_id (read-only)."""
    p = market_db_path or _default_market_db_path()
    if not p.is_file():
        return None
    mid = (market_event_id or "").strip()
    if not mid:
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
            SELECT market_event_id, open, high, low, close, candle_open_utc, canonical_symbol
            FROM market_bars_5m
            WHERE market_event_id = ?
            LIMIT 1
            """,
            (mid,),
        ).fetchone()
        if not row:
            return None
        keys = ("market_event_id", "open", "high", "low", "close", "candle_open_utc", "canonical_symbol")
        return dict(zip(keys, row))
    finally:
        conn.close()


def load_anna_economic_trades_for_strategy(
    strategy_id: str,
    *,
    db_path: Path | None = None,
    limit: int = 50_000,
) -> list[dict[str, Any]]:
    """
    Anna lane trades with economic P&L (paper/live). Excludes paper_stub for survival metrics.

    Rows include parsed context_snapshot when JSON present.
    """
    conn = connect_ledger(db_path or default_execution_ledger_path())
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, trace_id, created_at_utc
            FROM execution_trades
            WHERE strategy_id = ? AND lane = 'anna' AND mode IN ('paper', 'live')
            ORDER BY created_at_utc ASC, trade_id ASC
            LIMIT ?
            """,
            (strategy_id.strip(), int(limit)),
        )
        cols = [d[0] for d in cur.description]
        out: list[dict[str, Any]] = []
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            ctx_raw = row.get("context_snapshot_json")
            if ctx_raw:
                try:
                    row["context_snapshot"] = json.loads(ctx_raw)
                except (json.JSONDecodeError, TypeError):
                    row["context_snapshot"] = {}
            else:
                row["context_snapshot"] = {}
            out.append(row)
        return out
    finally:
        conn.close()


def trade_pnl_for_stats(row: dict[str, Any]) -> float | None:
    """Economic PnL only."""
    mode = (row.get("mode") or "").strip().lower()
    if not is_economic_mode(mode):
        return None
    p = row.get("pnl_usd")
    if p is None:
        return None
    try:
        return float(p)
    except (TypeError, ValueError):
        return None


def decisive_win_loss(pnl: float) -> str | None:
    if pnl > 0:
        return "win"
    if pnl < 0:
        return "loss"
    return None  # breakeven — exclude from decisive win rate
