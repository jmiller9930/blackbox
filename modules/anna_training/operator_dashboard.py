"""
Operator dashboard bundle — top-five Anna strategies, survival tests, market-event payload.

Selection logic is server-side only (Training Architect directive: no duplicated evaluation logic in UI).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from modules.anna_training.evaluation_summary import build_evaluation_summary
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

def _compact_qel_for_dashboard(body: dict[str, Any]) -> dict[str, Any]:
    """Small QEL slice for operator bundle — same fields as /evaluation-summary, no raw engine blobs."""
    if not body.get("ok"):
        return {
            "ok": False,
            "error": body.get("error"),
            "detail": body.get("detail"),
        }
    return {
        "ok": True,
        "strategy_id": body.get("strategy_id"),
        "canonical_evaluation": body.get("canonical_evaluation"),
        "lifecycle": body.get("lifecycle"),
        "checkpoints": body.get("checkpoints"),
        "metrics": body.get("metrics"),
        "baseline_comparison": body.get("baseline_comparison"),
        "regime_summary": body.get("regime_summary"),
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


def select_ranked_anna_strategy_ids(*, db_path: Path | None = None, limit: int = 5) -> tuple[list[str], str]:
    """
    Anna strategy_ids sorted by lifecycle maturity and economic P&L (server-side rule).
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
    lim = max(1, int(limit))
    top = [sid for sid, _ in rows[:lim]]
    return top, TOP_FIVE_RULE_DESCRIPTION


def select_top_five_anna_strategy_ids(*, db_path: Path | None = None) -> tuple[list[str], str]:
    """Returns up to five Anna strategy_ids (baseline handled separately)."""
    return select_ranked_anna_strategy_ids(db_path=db_path, limit=5)


def _overlay_limit_for_view_mode(view_mode: str) -> int:
    vm = (view_mode or "operator").strip().lower()
    if vm == "expanded":
        return 12
    if vm == "full":
        return 10_000
    return 5


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
    Full market-event-view payload plus operator_dashboard block (ranked strategies, survival tests).
    """
    base = build_market_event_view(qs)
    if not base.get("ok"):
        return base

    def _one(name: str) -> str | None:
        v = (qs.get(name) or [None])[0]
        return (str(v) if v is not None else "").strip() or None

    vm = (_one("view_mode") or "operator").strip().lower()
    if vm not in ("operator", "expanded", "full"):
        vm = "operator"

    db_path = default_execution_ledger_path()
    lim = _overlay_limit_for_view_mode(vm)
    ranked, rule = select_ranked_anna_strategy_ids(db_path=db_path, limit=lim)
    survival = query_active_survival_tests(db_path=db_path)
    lifecycle_map = query_lifecycle_by_strategy(db_path=db_path)

    mid_ev = base.get("market_event_id")
    mpath_arg: Path | None = None
    if base.get("market_data_path"):
        try:
            mp = Path(str(base["market_data_path"]))
            if mp.exists():
                mpath_arg = mp
        except Exception:
            mpath_arg = None

    qel_summaries: dict[str, Any] = {}
    if mid_ev:
        for sid in ranked[:5]:
            qs = {"strategy_id": [sid], "market_event_id": [str(mid_ev)]}
            summ = build_evaluation_summary(qs, db_path=db_path, market_db_path=mpath_arg)
            qel_summaries[sid] = _compact_qel_for_dashboard(summ)

    od = {
        "schema": "anna_operator_dashboard_v1",
        "view_mode": vm,
        "top_five_selection_rule": rule,
        "ranked_strategy_ids": ranked,
        "top_five_strategy_ids": ranked[:5] if len(ranked) >= 5 else ranked,
        "lifecycle_by_strategy_id": lifecycle_map,
        "survival_tests_active": survival,
        "qel_summaries": qel_summaries,
    }
    base["operator_dashboard"] = od

    ev = base.get("event") or {}
    bar = ev.get("bar") or {}
    sym = bar.get("canonical_symbol")
    tf = bar.get("timeframe")
    hist = (base.get("chart") or {}).get("history_bars") or []
    allowed_overlay = None if vm == "full" else ranked
    base["chart_overlay"] = build_chart_overlay(
        history_bars=list(hist) if isinstance(hist, list) else [],
        symbol=str(sym) if sym else None,
        timeframe=str(tf) if tf else None,
        allowed_anna_strategy_ids=allowed_overlay,
        survival_tests_active=survival,
        db_path=db_path,
    )
    return base
