"""
User-facing evaluation summary (QEL) — judgment view, not raw engine dumps.

Reads execution ledger + QEL tables only (authoritative). Optional market_event_id scopes
event slice metrics and baseline comparison for that bar.
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
from modules.anna_training.quantitative_evaluation_layer.checkpoint_config import load_survival_config
from modules.anna_training.quantitative_evaluation_layer.constants import DECISION_DROP, DECISION_SURVIVE
from modules.anna_training.quantitative_evaluation_layer.ledger_cohort import (
    decisive_win_loss,
    fetch_bar_by_market_event_id,
    load_anna_economic_trades_for_strategy,
    trade_pnl_for_stats,
)
from modules.anna_training.quantitative_evaluation_layer.regime_tags_v1 import regime_tags_v1_from_bar
from modules.anna_training.quant_metrics import max_drawdown_usd

SCHEMA_VERSION = "anna_evaluation_summary_v1"
CANONICAL_EVALUATION_SCHEMA = "canonical_evaluation_v1"
CANONICAL_EVALUATION_VERSION = "1"

# UI-facing labels; internal checkpoint keys stay stable.
CHECKPOINT_LABELS: dict[str, str] = {
    "min_economic_trades": "Minimum trades",
    "min_distinct_market_events": "Distinct market events",
    "min_calendar_span_days": "Time exposure (calendar span)",
    "distinctiveness_hash": "Distinctiveness (hypothesis)",
    "min_regime_vol_buckets": "Regime coverage (volatility buckets)",
    "min_performance": "Performance threshold",
}

PHASE_LABELS: dict[str, str] = {
    "experiment": "Exploratory",
    "test": "Under survival test",
    "candidate": "Candidate",
    "validated_strategy": "Validated (internal)",
    "promotion_ready": "Ready for human promotion review",
    "promoted": "Promoted",
    "archived": "Archived",
}


def _conn(db_path: Path | None) -> sqlite3.Connection:
    c = connect_ledger(db_path or default_execution_ledger_path())
    ensure_execution_ledger_schema(c)
    return c


def _ordered_pnls(trades: list[dict[str, Any]]) -> list[float]:
    rows = sorted(trades, key=lambda t: str(t.get("created_at_utc") or ""))
    out: list[float] = []
    for t in rows:
        p = trade_pnl_for_stats(t)
        if p is not None:
            out.append(p)
    return out


def _cohort_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = _ordered_pnls(trades)
    n = len(trades)
    total = sum(pnls) if pnls else 0.0
    wins = losses = 0
    for p in pnls:
        d = decisive_win_loss(p)
        if d == "win":
            wins += 1
        elif d == "loss":
            losses += 1
    decisive = wins + losses
    wr = round(wins / decisive, 6) if decisive else None
    max_dd, final_eq = max_drawdown_usd(pnls) if pnls else (0.0, 0.0)
    return {
        "trade_count": n,
        "win_rate": wr,
        "pnl_usd": round(total, 8),
        "max_drawdown_usd": round(max_dd, 8),
        "final_equity_usd": round(final_eq, 8),
    }


def _regime_breakdown(
    trades: list[dict[str, Any]],
    *,
    market_db_path: Path | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Vol buckets seen + per-bucket stats."""
    cfg = load_survival_config()
    rv = cfg.get("regime_v1") or {}
    buckets_seen: set[str] = set()
    agg: dict[str, dict[str, Any]] = {}

    for t in trades:
        mid = str(t.get("market_event_id") or "")
        bar = fetch_bar_by_market_event_id(mid, market_db_path=market_db_path)
        ctx = t.get("context_snapshot") if isinstance(t.get("context_snapshot"), dict) else {}
        gs = ctx.get("gate_state") if isinstance(ctx, dict) else None
        tags = regime_tags_v1_from_bar(
            bar,
            vol_low_below=float(rv.get("vol_low_below", 0.003)),
            vol_mid_below=float(rv.get("vol_mid_below", 0.012)),
            flat_abs_pct=float(rv.get("flat_abs_pct", 0.0005)),
            gate_state=str(gs) if gs else None,
        )
        vb = tags.get("vol_bucket")
        if not vb:
            continue
        buckets_seen.add(vb)
        if vb not in agg:
            agg[vb] = {"bucket": vb, "trades": 0, "wins": 0, "losses": 0, "net_pnl_usd": 0.0}
        pnl = trade_pnl_for_stats(t)
        if pnl is None:
            continue
        agg[vb]["trades"] += 1
        agg[vb]["net_pnl_usd"] = round(float(agg[vb]["net_pnl_usd"]) + pnl, 8)
        d = decisive_win_loss(pnl)
        if d == "win":
            agg[vb]["wins"] += 1
        elif d == "loss":
            agg[vb]["losses"] += 1

    ordered = sorted(buckets_seen)
    rows = [agg[k] for k in sorted(agg.keys())]
    return ordered, rows


def _stability_hint(vol_rows: list[dict[str, Any]]) -> str | None:
    if len(vol_rows) < 2:
        return "limited_regime_diversity"
    nets = [float(r.get("net_pnl_usd") or 0) for r in vol_rows]
    if all(n >= 0 for n in nets):
        return "non_negative_across_seen_vol_buckets"
    if all(n <= 0 for n in nets):
        return "negative_across_seen_vol_buckets"
    return "mixed_across_vol_buckets"


def _baseline_compare_at_event(
    market_event_id: str,
    strategy_pnl: float | None,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            """
            SELECT pnl_usd FROM execution_trades
            WHERE lane = 'baseline' AND strategy_id = ?
              AND market_event_id = ? AND mode IN ('paper', 'live')
            LIMIT 1
            """,
            (RESERVED_STRATEGY_BASELINE, market_event_id.strip()),
        )
        row = cur.fetchone()
        if not row or row[0] is None or strategy_pnl is None:
            return {"available": False, "reason": "missing_baseline_or_strategy_pnl"}
        bp = float(row[0])
        sp = float(strategy_pnl)
        delta = sp - bp
        if abs(delta) < 1e-9:
            direction = "same"
        elif delta > 0:
            direction = "better"
        else:
            direction = "worse"
        return {
            "available": True,
            "direction": direction,
            "baseline_pnl_usd": round(bp, 8),
            "strategy_pnl_usd": round(sp, 8),
            "delta_pnl_usd": round(delta, 8),
        }
    finally:
        conn.close()


def build_evaluation_summary(
    qs: dict[str, list[str]],
    *,
    db_path: Path | None = None,
    market_db_path: Path | None = None,
) -> dict[str, Any]:
    """
    GET query params: strategy_id (required), market_event_id (optional).

    Returns structured judgment view — no raw math_engine / full_stack blobs.
    """
    strategy_id = (qs.get("strategy_id") or [""])[0].strip()
    if not strategy_id:
        return {
            "ok": False,
            "error": "missing_strategy_id",
            "detail": "Provide strategy_id=",
            "schema": SCHEMA_VERSION,
        }
    mid = (qs.get("market_event_id") or [""])[0].strip() or None

    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "SELECT lifecycle_state, parent_strategy_id FROM strategy_registry WHERE strategy_id = ?",
            (strategy_id,),
        )
        reg = cur.fetchone()
        lifecycle_state = str(reg[0]) if reg and reg[0] else "experiment"
        parent_strategy_id = str(reg[1]) if reg and reg[1] else None
        if not reg:
            lifecycle_state = "unknown"
    finally:
        conn.close()

    all_trades = load_anna_economic_trades_for_strategy(strategy_id, db_path=db_path)
    event_trades = [t for t in all_trades if mid and str(t.get("market_event_id") or "") == mid]

    metrics_strategy = _cohort_metrics(all_trades)
    metrics_event = _cohort_metrics(event_trades) if mid else None

    vol_seen, vol_rows = _regime_breakdown(all_trades, market_db_path=market_db_path)
    stability = _stability_hint(vol_rows)

    # Latest active survival test + aggregate checkpoint outcomes across all tests for this strategy
    conn = _conn(db_path)
    test_id: str | None = None
    test_status: str | None = None
    completed_survived_count = 0
    try:
        cur = conn.execute(
            """
            SELECT test_id, status FROM anna_survival_tests
            WHERE strategy_id = ?
            ORDER BY (CASE WHEN status = 'active' THEN 0 ELSE 1 END), created_at_utc DESC
            LIMIT 1
            """,
            (strategy_id,),
        )
        tr = cur.fetchone()
        if tr:
            test_id, test_status = str(tr[0]), str(tr[1])
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM anna_survival_tests
            WHERE strategy_id = ? AND status = 'completed_survived'
            """,
            (strategy_id,),
        )
        cr = cur.fetchone()
        completed_survived_count = int(cr[0]) if cr else 0
    finally:
        conn.close()

    checkpoint_rows: list[dict[str, Any]] = []
    last_decision: str | None = None
    last_eval_at: str | None = None

    cfg = load_survival_config()
    cp_cfg = cfg.get("checkpoints") or {}
    configured_order = [
        "min_economic_trades",
        "min_distinct_market_events",
        "min_calendar_span_days",
        "distinctiveness_hash",
        "min_regime_vol_buckets",
        "min_performance",
    ]

    latest_by_name: dict[str, tuple[str, str]] = {}
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            """
            SELECT r.checkpoint_name, r.decision, r.evaluated_at_utc
            FROM anna_survival_evaluation_runs r
            JOIN anna_survival_tests t ON t.test_id = r.test_id
            WHERE t.strategy_id = ?
            ORDER BY r.evaluated_at_utc DESC
            """,
            (strategy_id,),
        )
        for name, dec, ev_at in cur.fetchall():
            n = str(name)
            if n not in latest_by_name:
                latest_by_name[n] = (str(dec), str(ev_at))
        cur2 = conn.execute(
            """
            SELECT r.decision, r.evaluated_at_utc
            FROM anna_survival_evaluation_runs r
            JOIN anna_survival_tests t ON t.test_id = r.test_id
            WHERE t.strategy_id = ?
            ORDER BY r.evaluated_at_utc DESC
            LIMIT 1
            """,
            (strategy_id,),
        )
        lr = cur2.fetchone()
        if lr:
            last_decision, last_eval_at = str(lr[0]), str(lr[1])
    finally:
        conn.close()

    for i, key in enumerate(configured_order):
        spec = cp_cfg.get(key)
        if spec is not None and not spec.get("enabled", True):
            continue
        if key in latest_by_name:
            dec, ev_at = latest_by_name[key]
            result = "PASS" if dec == DECISION_SURVIVE else "FAIL"
        else:
            result = "PENDING"
            ev_at = ""
        checkpoint_rows.append(
            {
                "checkpoint_key": key,
                "checkpoint_label": CHECKPOINT_LABELS.get(key, key),
                "result": result,
                "evaluated_at_utc": ev_at or None,
                "order": i + 1,
            }
        )

    baseline_comparison: dict[str, Any] = {"available": False}
    if mid:
        st_pnl = None
        for t in event_trades:
            st_pnl = trade_pnl_for_stats(t)
            if st_pnl is not None:
                break
        baseline_comparison = _baseline_compare_at_event(mid, st_pnl, db_path=db_path)

    regime_summary = {
        "volatility_buckets_seen": vol_seen,
        "by_vol_bucket": vol_rows,
        "performance_note": (
            "Higher net P&L in a bucket does not imply edge — descriptive only."
            if vol_rows
            else "No vol-bucket tags yet (missing bars or no economic trades)."
        ),
    }

    metrics_out = {
        "scope": "event" if mid else "strategy",
        "strategy_cohort": metrics_strategy,
        "stability_hint": stability,
    }
    if mid and metrics_event is not None:
        metrics_out["at_market_event"] = metrics_event

    body: dict[str, Any] = {
        "ok": True,
        "schema": SCHEMA_VERSION,
        "subsystem": "Quantitative Evaluation Layer",
        "strategy_id": strategy_id,
        "market_event_id": mid,
        "parent_strategy_id": parent_strategy_id,
        "lifecycle": {
            "lifecycle_state": lifecycle_state,
            "current_phase": PHASE_LABELS.get(lifecycle_state, lifecycle_state),
            "last_checkpoint_decision": last_decision,
            "last_evaluated_at_utc": last_eval_at,
            "active_test_id": test_id,
            "test_status": test_status,
            "completed_survived_count": completed_survived_count,
        },
        "checkpoints": checkpoint_rows,
        "metrics": metrics_out,
        "regime_summary": regime_summary,
        "baseline_comparison": baseline_comparison,
        "ledger_path": str(db_path or default_execution_ledger_path()),
    }
    body["canonical_evaluation"] = _build_canonical_evaluation_surface(body)
    return body


def _build_canonical_evaluation_surface(body: dict[str, Any]) -> dict[str, Any]:
    """Stable, versioned judgment surface for API/UI — no raw DB rows required."""
    lc = body.get("lifecycle") or {}
    st = str(lc.get("lifecycle_state") or "")
    readiness = "not_ready"
    if st == "promotion_ready":
        readiness = "promotion_ready"
    elif st == "promoted":
        readiness = "promoted"
    elif st == "archived":
        readiness = "archived"
    elif st in ("candidate", "validated_strategy"):
        readiness = "advancing"

    return {
        "schema": CANONICAL_EVALUATION_SCHEMA,
        "schema_version": CANONICAL_EVALUATION_VERSION,
        "strategy_id": body.get("strategy_id"),
        "market_event_id": body.get("market_event_id"),
        "lifecycle_state": st,
        "current_phase": lc.get("current_phase"),
        "last_checkpoint_decision": lc.get("last_checkpoint_decision"),
        "last_evaluated_at_utc": lc.get("last_evaluated_at_utc"),
        "active_test_id": lc.get("active_test_id"),
        "test_status": lc.get("test_status"),
        "completed_survived_count": lc.get("completed_survived_count"),
        "readiness_state": readiness,
        "promotion_ready_eligible": st == "promotion_ready",
        "checkpoints": body.get("checkpoints") or [],
        "metrics": body.get("metrics") or {},
        "regime_summary": body.get("regime_summary") or {},
        "baseline_comparison": body.get("baseline_comparison"),
    }
