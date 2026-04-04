"""
QEL survival engine: binary checkpoint decisions (survive | drop) only.

Insufficient data for a checkpoint ⇒ skip this run (no evaluation row). Not a third outcome.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, default_execution_ledger_path, ensure_execution_ledger_schema
from modules.anna_training.store import utc_now_iso

from .checkpoint_config import checkpoint_summary_header, load_survival_config
from .constants import DECISION_DROP, DECISION_SURVIVE, QEL_ENGINE_VERSION, QEL_SUBSYSTEM_NAME
from .ledger_cohort import (
    decisive_win_loss,
    fetch_bar_by_market_event_id,
    load_anna_economic_trades_for_strategy,
    trade_pnl_for_stats,
)
from .lifecycle_advance import all_enabled_checkpoints_survived
from .regime_tags_v1 import regime_tags_v1_from_bar


def _parse_ts_utc(s: str | None) -> datetime | None:
    if not s or not str(s).strip():
        return None
    raw = str(s).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _determinism_hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _base_summary(
    checkpoint_name: str,
    decision: str,
    strategy_id: str,
    test_id: str,
    **extra: Any,
) -> dict[str, Any]:
    out = checkpoint_summary_header(
        checkpoint_name=checkpoint_name,
        decision=decision,
        strategy_id=strategy_id,
        test_id=test_id,
        engine_version=QEL_ENGINE_VERSION,
    )
    out["qel_subsystem"] = QEL_SUBSYSTEM_NAME
    out.update(extra)
    return out


def _persist_run(
    conn: sqlite3.Connection,
    test_id: str,
    checkpoint_name: str,
    decision: str,
    summary: dict[str, Any],
    trades: list[dict[str, Any]],
    trade_ids: list[str],
    rv: dict[str, Any],
) -> None:
    rid = str(uuid.uuid4())
    now = utc_now_iso()
    trade_ids_sorted = sorted(trade_ids)
    dhash = _determinism_hash([test_id, checkpoint_name, QEL_ENGINE_VERSION, json.dumps(trade_ids_sorted)])
    metrics = {
        "trade_count_economic": len(trades),
        "trade_ids_sample": trade_ids_sorted[:12],
    }
    conn.execute(
        """
        INSERT INTO anna_survival_evaluation_runs (
          run_id, test_id, checkpoint_name, evaluated_at_utc, decision,
          checkpoint_summary_json, metrics_snapshot_json, regime_coverage_json,
          engine_version, determinism_inputs_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            test_id,
            checkpoint_name,
            now,
            decision,
            json.dumps(summary, ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False),
            json.dumps({"regime_v1_params": rv}, ensure_ascii=False),
            QEL_ENGINE_VERSION,
            dhash,
        ),
    )


def run_survival_checkpoints_for_test(
    test_id: str,
    *,
    db_path: Path | None = None,
    market_db_path: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run checkpoints in fixed order. Each executed checkpoint persists one row (survive or drop).

    Stops after first *drop* on checkpoints that halt the pipeline (distinctiveness, min_performance).
    """
    cfg = config if config is not None else load_survival_config()
    cp = cfg.get("checkpoints") or {}
    rv = cfg.get("regime_v1") or {}

    conn = connect_ledger(db_path or default_execution_ledger_path())
    ensure_execution_ledger_schema(conn)
    try:
        cur = conn.execute(
            """
            SELECT test_id, strategy_id, hypothesis_hash, status
            FROM anna_survival_tests
            WHERE test_id = ?
            """,
            (test_id.strip(),),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "reason": "test_not_found", "runs": []}
        tid, strategy_id, hyp_hash, status = row
        if status != "active":
            return {"ok": False, "reason": "test_not_active", "status": status, "runs": []}

        sid = str(strategy_id)
        trades = load_anna_economic_trades_for_strategy(sid, db_path=db_path)
        trade_ids = [str(t.get("trade_id") or "") for t in trades]
        mids = {str(t.get("market_event_id") or "") for t in trades if t.get("market_event_id")}

        runs_out: list[dict[str, Any]] = []
        halted = False

        # 1) min economic trades
        spec = cp.get("min_economic_trades") or {}
        if spec.get("enabled", True):
            min_n = int(spec.get("min_count", 5))
            if len(trades) >= min_n:
                summ = _base_summary(
                    "min_economic_trades",
                    DECISION_SURVIVE,
                    sid,
                    tid,
                    message="Economic trade count meets minimum.",
                    thresholds_applied={"min_economic_trades": min_n},
                    counts={"economic_trades": len(trades)},
                )
                _persist_run(conn, tid, "min_economic_trades", DECISION_SURVIVE, summ, trades, trade_ids, rv)
                runs_out.append(summ)

        # 2) distinct market events
        spec = cp.get("min_distinct_market_events") or {}
        if spec.get("enabled", True):
            min_m = int(spec.get("min_count", 5))
            if len(mids) >= min_m:
                summ = _base_summary(
                    "min_distinct_market_events",
                    DECISION_SURVIVE,
                    sid,
                    tid,
                    message="Distinct market_event_id count meets minimum.",
                    thresholds_applied={"min_distinct_market_events": min_m},
                    counts={"distinct_market_events": len(mids)},
                )
                _persist_run(conn, tid, "min_distinct_market_events", DECISION_SURVIVE, summ, trades, trade_ids, rv)
                runs_out.append(summ)

        # 3) calendar span
        spec = cp.get("min_calendar_span_days") or {}
        if spec.get("enabled", True):
            min_days = float(spec.get("min_days", 1))
            ts_list = [_parse_ts_utc(str(t.get("created_at_utc"))) for t in trades]
            ts_list = [x for x in ts_list if x is not None]
            if len(ts_list) >= 2:
                span = (max(ts_list) - min(ts_list)).total_seconds() / 86400.0
                if span >= min_days:
                    summ = _base_summary(
                        "min_calendar_span_days",
                        DECISION_SURVIVE,
                        sid,
                        tid,
                        message="Calendar span meets minimum.",
                        thresholds_applied={"min_calendar_span_days": min_days},
                        counts={"span_days_rounded": round(span, 4)},
                    )
                    _persist_run(conn, tid, "min_calendar_span_days", DECISION_SURVIVE, summ, trades, trade_ids, rv)
                    runs_out.append(summ)

        # 4) distinctiveness (always runs when enabled — no skip; binary outcome)
        spec = cp.get("distinctiveness_hash") or {}
        if spec.get("enabled", True):
            cur2 = conn.execute(
                """
                SELECT test_id, strategy_id FROM anna_survival_tests
                WHERE hypothesis_hash = ? AND status = 'active' AND test_id != ?
                """,
                (str(hyp_hash), str(tid)),
            )
            dup = cur2.fetchall()
            if dup:
                summ = _base_summary(
                    "distinctiveness_hash",
                    DECISION_DROP,
                    sid,
                    tid,
                    message="Another active test shares the same normalized hypothesis hash.",
                    duplicate_tests=[{"test_id": str(a[0]), "strategy_id": str(a[1])} for a in dup],
                    hypothesis_hash=str(hyp_hash),
                )
                _persist_run(conn, tid, "distinctiveness_hash", DECISION_DROP, summ, trades, trade_ids, rv)
                runs_out.append(summ)
                halted = True
            else:
                summ = _base_summary(
                    "distinctiveness_hash",
                    DECISION_SURVIVE,
                    sid,
                    tid,
                    message="No conflicting active test with identical hypothesis hash.",
                    hypothesis_hash=str(hyp_hash),
                )
                _persist_run(conn, tid, "distinctiveness_hash", DECISION_SURVIVE, summ, trades, trade_ids, rv)
                runs_out.append(summ)

        if halted:
            conn.execute(
                "UPDATE anna_survival_tests SET status = 'completed_dropped' WHERE test_id = ?",
                (tid,),
            )
            conn.commit()
            return _result_ok(tid, sid, runs_out, halted=True)

        # 5) regime vol buckets
        spec = cp.get("min_regime_vol_buckets") or {}
        if spec.get("enabled", True):
            min_buckets = int(spec.get("min_distinct_vol_buckets", 2))
            min_per = int(spec.get("min_trades_per_bucket", 1))
            vols: dict[str, int] = {}
            for t in trades:
                mid = str(t.get("market_event_id") or "")
                bar = fetch_bar_by_market_event_id(mid, market_db_path=market_db_path)
                gs = None
                ctx = t.get("context_snapshot") or {}
                if isinstance(ctx, dict):
                    gs = ctx.get("gate_state")
                tags = regime_tags_v1_from_bar(
                    bar,
                    vol_low_below=float(rv.get("vol_low_below", 0.003)),
                    vol_mid_below=float(rv.get("vol_mid_below", 0.012)),
                    flat_abs_pct=float(rv.get("flat_abs_pct", 0.0005)),
                    gate_state=str(gs) if gs else None,
                )
                vb = tags.get("vol_bucket")
                if vb:
                    vols[vb] = vols.get(vb, 0) + 1
            distinct_ok = {k for k, v in vols.items() if v >= min_per}
            if len(distinct_ok) >= min_buckets:
                summ = _base_summary(
                    "min_regime_vol_buckets",
                    DECISION_SURVIVE,
                    sid,
                    tid,
                    message="Volatility bucket spread meets minimum.",
                    thresholds_applied={
                        "min_distinct_vol_buckets": min_buckets,
                        "min_trades_per_bucket": min_per,
                    },
                    regime_vol_counts=vols,
                )
                _persist_run(conn, tid, "min_regime_vol_buckets", DECISION_SURVIVE, summ, trades, trade_ids, rv)
                runs_out.append(summ)

        # 6) performance floors
        spec = cp.get("min_performance") or {}
        if spec.get("enabled", True):
            min_pnl = float(spec.get("min_total_pnl_usd", -1e9))
            min_wr = float(spec.get("min_win_rate_decisive", 0.0))
            total = 0.0
            wins = losses = 0
            for t in trades:
                pnl = trade_pnl_for_stats(t)
                if pnl is None:
                    continue
                total += pnl
                d = decisive_win_loss(pnl)
                if d == "win":
                    wins += 1
                elif d == "loss":
                    losses += 1
            decisive = wins + losses
            wr = (wins / decisive) if decisive else 0.0
            if total < min_pnl or wr < min_wr:
                dec = DECISION_DROP
                halted = True
            else:
                dec = DECISION_SURVIVE
            summ = _base_summary(
                "min_performance",
                dec,
                sid,
                tid,
                message="Performance checkpoint vs configured floors.",
                thresholds_applied={"min_total_pnl_usd": min_pnl, "min_win_rate_decisive": min_wr},
                metrics={
                    "total_pnl_usd": round(total, 8),
                    "decisive_trades": decisive,
                    "win_rate_decisive": round(wr, 8),
                },
            )
            _persist_run(conn, tid, "min_performance", dec, summ, trades, trade_ids, rv)
            runs_out.append(summ)

        if halted:
            conn.execute(
                "UPDATE anna_survival_tests SET status = 'completed_dropped' WHERE test_id = ?",
                (tid,),
            )
            conn.commit()
            return _result_ok(tid, sid, runs_out, halted=True)

        lifecycle_advance: dict[str, Any] | None = None
        if all_enabled_checkpoints_survived(conn, tid, cfg):
            conn.execute(
                "UPDATE anna_survival_tests SET status = 'completed_survived' WHERE test_id = ?",
                (tid,),
            )
            conn.commit()
            from .lifecycle_advance import apply_lifecycle_after_full_survival

            lifecycle_advance = apply_lifecycle_after_full_survival(
                completed_test_id=tid,
                strategy_id=sid,
                db_path=db_path,
            )
        else:
            conn.commit()

        return _result_ok(tid, sid, runs_out, halted=False, lifecycle_advance=lifecycle_advance)
    finally:
        conn.close()


def _result_ok(
    test_id: str,
    strategy_id: str,
    runs: list[dict[str, Any]],
    *,
    halted: bool,
    lifecycle_advance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": True,
        "subsystem": QEL_SUBSYSTEM_NAME,
        "test_id": test_id,
        "strategy_id": strategy_id,
        "runs": runs,
        "stopped_at_drop": halted,
    }
    if lifecycle_advance:
        out["lifecycle_advance"] = lifecycle_advance
    return out
