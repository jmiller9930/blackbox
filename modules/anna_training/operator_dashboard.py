"""
Operator dashboard bundle — top-five Anna strategies, survival tests, market-event payload.

Selection logic is server-side only (Training Architect directive: no duplicated evaluation logic in UI).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    connect_ledger,
    default_execution_ledger_path,
    ensure_execution_ledger_schema,
)
from modules.anna_training.chart_overlay import build_chart_overlay
from modules.anna_training.market_event_view import build_market_event_view
from modules.anna_training.quantitative_evaluation_layer.constants import (
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_CANDIDATE,
    LIFECYCLE_EXPERIMENT,
    LIFECYCLE_PROMOTED,
    LIFECYCLE_PROMOTION_READY,
    LIFECYCLE_TEST,
    LIFECYCLE_VALIDATED_STRATEGY,
)

# Higher = more mature for default top-five ordering (deterministic).
_LIFECYCLE_MATURITY_RANK: dict[str, int] = {
    LIFECYCLE_PROMOTED: 600,
    LIFECYCLE_PROMOTION_READY: 500,
    LIFECYCLE_VALIDATED_STRATEGY: 400,
    LIFECYCLE_CANDIDATE: 300,
    LIFECYCLE_TEST: 200,
    LIFECYCLE_EXPERIMENT: 100,
    LIFECYCLE_ARCHIVED: 0,
}

TOP_FIVE_RULE_DESCRIPTION = (
    "Default top-five Anna strategies (max 5 lines, excluding baseline): "
    "sort by (1) lifecycle maturity rank descending — promoted > promotion_ready > "
    "validated_strategy > candidate > test > experiment > archived; "
    "(2) total economic P&L USD (anna lane, paper and live) descending; "
    "(3) strategy_id ascending as final tie-break."
)


def _economic_pnl_sum_by_strategy(conn: sqlite3.Connection) -> dict[str, float]:
    cur = conn.execute(
        """
        SELECT strategy_id, COALESCE(SUM(pnl_usd), 0.0)
        FROM execution_trades
        WHERE lane = 'anna' AND mode IN ('paper', 'live') AND pnl_usd IS NOT NULL
        GROUP BY strategy_id
        """
    )
    return {str(r[0]): float(r[1]) for r in cur.fetchall()}


def select_top_five_anna_strategy_ids(*, db_path: Path | None = None) -> tuple[list[str], str]:
    """
    Returns up to five Anna strategy_ids for chart surfacing (baseline handled separately).
    """
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        pnl_by = _economic_pnl_sum_by_strategy(conn)
        cur = conn.execute(
            """
            SELECT strategy_id, lifecycle_state
            FROM strategy_registry
            WHERE strategy_id != ?
            ORDER BY strategy_id ASC
            """,
            (RESERVED_STRATEGY_BASELINE,),
        )
        rows = [(str(r[0]), str(r[1] or LIFECYCLE_EXPERIMENT)) for r in cur.fetchall()]
    finally:
        conn.close()

    def sort_key(item: tuple[str, str]) -> tuple[int, float, str]:
        sid, lc = item
        rank = _LIFECYCLE_MATURITY_RANK.get(lc, 50)
        pnl = pnl_by.get(sid, 0.0)
        return (-rank, -pnl, sid)

    rows.sort(key=sort_key)
    top = [sid for sid, _ in rows[:5]]
    return top, TOP_FIVE_RULE_DESCRIPTION


def query_active_survival_tests(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT test_id, strategy_id, status, hypothesis_json, created_at_utc
            FROM anna_survival_tests
            WHERE status = 'active'
            ORDER BY created_at_utc ASC
            """
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def query_lifecycle_by_strategy(*, db_path: Path | None = None) -> dict[str, str]:
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute("SELECT strategy_id, lifecycle_state FROM strategy_registry")
        return {str(r[0]): str(r[1] or LIFECYCLE_EXPERIMENT) for r in cur.fetchall()}
    finally:
        conn.close()


def build_operator_dashboard(qs: dict[str, list[str]]) -> dict[str, Any]:
    """
    Full market-event-view payload plus operator_dashboard block (top-five, survival tests, lifecycle map).
    """
    base = build_market_event_view(qs)
    if not base.get("ok"):
        return base

    db_path = default_execution_ledger_path()
    top_five, rule = select_top_five_anna_strategy_ids(db_path=db_path)
    survival = query_active_survival_tests(db_path=db_path)
    lifecycle_map = query_lifecycle_by_strategy(db_path=db_path)

    od = {
        "schema": "anna_operator_dashboard_v1",
        "top_five_selection_rule": rule,
        "top_five_strategy_ids": top_five,
        "lifecycle_by_strategy_id": lifecycle_map,
        "survival_tests_active": survival,
    }
    base["operator_dashboard"] = od

    ev = base.get("event") or {}
    bar = ev.get("bar") or {}
    sym = bar.get("canonical_symbol")
    tf = bar.get("timeframe")
    hist = (base.get("chart") or {}).get("history_bars") or []
    base["chart_overlay"] = build_chart_overlay(
        history_bars=list(hist) if isinstance(hist, list) else [],
        symbol=str(sym) if sym else None,
        timeframe=str(tf) if tf else None,
        top_five_strategy_ids=top_five,
        survival_tests_active=survival,
        db_path=db_path,
    )
    return base
