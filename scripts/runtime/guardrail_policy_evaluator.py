#!/usr/bin/env python3
"""
Phase 2.11 — Guardrail policy evaluator: operating mode from decision context + system trend.

Rule-only; no ML, no trades, no mutation except optional --store.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root
from analyst_decision_engine import load_latest_stored_decision_context
from decision_context_builder import build_payload
from insight_trend_tracker import build_system_trend, load_recent_system_insights


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_latest_stored_system_trend(conn) -> dict:
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[System Trend]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        raise LookupError("no stored [System Trend] task found")
    data = json.loads(row[1])
    if data.get("kind") != "system_trend_v1":
        raise ValueError("latest trend task is not system_trend_v1")
    return data


def load_latest_stored_system_insight(conn) -> tuple[str | None, dict | None]:
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[System Insight]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        return None, None
    try:
        data = json.loads(row[1])
    except json.JSONDecodeError:
        return None, None
    if data.get("kind") != "system_insight_v1":
        return None, None
    return row[0], data


def evaluate_mode(
    ctx: dict,
    trend: dict,
    insight: dict | None,
) -> tuple[str, str, dict[str, Any], list[str]]:
    """
    Return (mode, reasoning, supporting_signals, caution_flags_out).
    mode: FROZEN | CAUTION | NORMAL
    """
    readiness = ctx.get("system_readiness")
    hs = ctx.get("health_summary") or {}
    alert_s = ctx.get("alert_summary") or {}
    ctx_flags = list(ctx.get("caution_flags") or [])

    open_alerts = int(alert_s.get("open_unacknowledged_count") or 0)
    fail_rows = int(hs.get("recent_failure_row_count") or 0)

    trend_flags = list(trend.get("flags") or [])
    ot = trend.get("outcome_trend") or {}
    od = ot.get("outcome_delta_recent_minus_prior") or {}
    roc = ot.get("recent_outcome_counts") or {}
    poc = ot.get("prior_outcome_counts") or {}

    at = trend.get("alignment_trend") or {}
    mis_r = int(at.get("misaligned_recent") or 0)
    mis_p = int(at.get("misaligned_prior") or 0)

    rt = trend.get("risk_trend") or {}
    persistent = list(rt.get("persistent_flags") or [])

    st = trend.get("structural_trend") or {}
    rstr = st.get("recent_structural_totals") or {}
    null_sum = int(rstr.get("null_alert_link_episodes") or 0) + int(
        rstr.get("null_coordination_link_episodes") or 0
    )

    supporting: dict[str, Any] = {
        "readiness": readiness,
        "open_alerts": open_alerts,
        "recent_health_fail_rows": fail_rows,
        "trend_flags": trend_flags,
        "misaligned_recent": mis_r,
        "misaligned_prior": mis_p,
        "persistent_flags": persistent,
        "outcome_failure_delta": int(od.get("FAILURE") or 0),
        "outcome_unknown_delta": int(od.get("UNKNOWN") or 0),
        "recent_failure_count": int(roc.get("FAILURE") or 0),
        "prior_failure_count": int(poc.get("FAILURE") or 0),
        "structural_null_link_episodes_sum_recent": null_sum,
    }

    out_caution = list(dict.fromkeys(ctx_flags + trend_flags))

    # --- FROZEN (highest priority) ---
    frozen_reasons: list[str] = []

    if readiness == "unstable":
        frozen_reasons.append("system_readiness is unstable")

    fail_delta = int(od.get("FAILURE") or 0)
    if fail_delta > 0 and int(roc.get("FAILURE") or 0) >= int(poc.get("FAILURE") or 0):
        frozen_reasons.append("failure outcomes increased in the recent trend window")

    if int(roc.get("FAILURE") or 0) >= 2 and int(poc.get("FAILURE") or 0) == 0:
        frozen_reasons.append("recent failure outcomes are dominant vs empty prior window")

    if "structural gaps high" in trend_flags and null_sum >= 2:
        frozen_reasons.append("structural gaps high with material null-link episode counts")

    if len(persistent) >= 3:
        frozen_reasons.append("three or more persistent caution patterns across insight runs")

    if "misalignment rising" in trend_flags and mis_r >= 2:
        frozen_reasons.append("misalignment rising with elevated misaligned counts")

    if frozen_reasons:
        return (
            "FROZEN",
            "Operating envelope frozen: " + "; ".join(frozen_reasons) + ".",
            supporting,
            out_caution,
        )

    # --- CAUTION ---
    caution_reasons: list[str] = []

    if readiness == "degraded":
        caution_reasons.append("system_readiness is degraded")

    if "misalignment rising" in trend_flags:
        caution_reasons.append("trend flags report misalignment rising")

    if "persistent alerts" in trend_flags or persistent:
        caution_reasons.append("persistent alert-related caution patterns in trends")

    if "structural gaps high" in trend_flags:
        caution_reasons.append("structural gaps high flagged in trend output")

    unk_delta = int(od.get("UNKNOWN") or 0)
    if unk_delta > 0 or int(roc.get("UNKNOWN") or 0) > int(poc.get("UNKNOWN") or 0):
        caution_reasons.append("unknown outcomes elevated or rising in trend window")

    if open_alerts > 0:
        caution_reasons.append(f"open unacknowledged alerts: {open_alerts}")

    if fail_rows > 3:
        caution_reasons.append(f"recent health FAIL rows material: {fail_rows}")

    if mis_r > mis_p and mis_r > 0:
        caution_reasons.append("misaligned episodes increased vs prior window")

    if caution_reasons:
        return (
            "CAUTION",
            "Caution posture: " + "; ".join(caution_reasons) + ".",
            supporting,
            out_caution,
        )

    # --- NORMAL ---
    if readiness == "healthy" and open_alerts == 0 and fail_rows <= 2:
        return (
            "NORMAL",
            "Healthy readiness with no material open alerts or health FAIL rows; trend signals not elevated.",
            supporting,
            out_caution,
        )

    # Conservative default
    return (
        "CAUTION",
        "Default caution: readiness not clearly healthy or residual signals remain.",
        supporting,
        out_caution,
    )


def _minimal_trend_baseline() -> dict[str, Any]:
    """Synthetic system_trend_v1-shaped dict for tests / defaults."""
    return {
        "kind": "system_trend_v1",
        "generated_at": _utc_now(),
        "window_size": 1,
        "flags": [],
        "outcome_trend": {
            "outcome_delta_recent_minus_prior": {
                "MONITORING": 0,
                "SUCCESS": 0,
                "FAILURE": 0,
                "UNKNOWN": 0,
                "NOT_APPLICABLE": 0,
            },
            "recent_outcome_counts": {
                "FAILURE": 0,
                "UNKNOWN": 0,
            },
            "prior_outcome_counts": {
                "FAILURE": 0,
                "UNKNOWN": 0,
            },
        },
        "alignment_trend": {"misaligned_recent": 0, "misaligned_prior": 0},
        "risk_trend": {"persistent_flags": []},
        "structural_trend": {
            "recent_structural_totals": {
                "null_alert_link_episodes": 0,
                "null_coordination_link_episodes": 0,
                "placeholder_episodes": 0,
            },
        },
    }


def run_local_branch_tests() -> dict[str, Any]:
    """Deterministic FROZEN / CAUTION / NORMAL checks (no DB)."""
    base_t = _minimal_trend_baseline()
    out: list[dict[str, Any]] = []

    ctx_frozen = {
        "system_readiness": "unstable",
        "alert_summary": {"open_unacknowledged_count": 0},
        "health_summary": {"recent_failure_row_count": 0},
        "caution_flags": [],
    }
    m, r, _, _ = evaluate_mode(ctx_frozen, base_t, None)
    out.append({"branch": "LOCAL: FROZEN (unstable readiness)", "mode": m, "matches": m == "FROZEN"})

    ctx_caution = {
        "system_readiness": "degraded",
        "alert_summary": {"open_unacknowledged_count": 0},
        "health_summary": {"recent_failure_row_count": 0},
        "caution_flags": [],
    }
    m2, _, _, _ = evaluate_mode(ctx_caution, base_t, None)
    out.append({"branch": "LOCAL: CAUTION (degraded readiness)", "mode": m2, "matches": m2 == "CAUTION"})

    ctx_normal = {
        "system_readiness": "healthy",
        "alert_summary": {"open_unacknowledged_count": 0},
        "health_summary": {"recent_failure_row_count": 0},
        "caution_flags": [],
    }
    m3, _, _, _ = evaluate_mode(ctx_normal, base_t, None)
    out.append({"branch": "LOCAL: NORMAL (healthy + quiet trend)", "mode": m3, "matches": m3 == "NORMAL"})

    return {"local_branch_tests": out, "all_pass": all(x["matches"] for x in out)}


def build_guardrail_document(
    db_path: Path,
    *,
    use_stored_context: bool,
    use_stored_trend: bool,
    include_insight_ref: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    trend_recent: int,
) -> dict[str, Any]:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)

    if use_stored_context:
        try:
            ctx = load_latest_stored_decision_context(conn)
        finally:
            conn.close()
    else:
        try:
            conn.close()
        except Exception:
            pass
        ctx = build_payload(db_path, health_limit, task_limit, alert_window)

    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)
    try:
        if use_stored_trend:
            trend = load_latest_stored_system_trend(conn)
        else:
            rows = load_recent_system_insights(conn, trend_recent)
            if not rows:
                raise LookupError(
                    "no [System Insight] tasks for live trend; use --use-latest-stored-trend or store insights first"
                )
            trend = build_system_trend(rows)

        insight_id: str | None = None
        insight_doc: dict | None = None
        if include_insight_ref:
            insight_id, insight_doc = load_latest_stored_system_insight(conn)
    finally:
        conn.close()

    mode, reasoning, supporting, cflags = evaluate_mode(ctx, trend, insight_doc)

    doc: dict[str, Any] = {
        "kind": "guardrail_policy_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "mode": mode,
        "reasoning": reasoning,
        "context_reference": {
            "kind": ctx.get("kind"),
            "generated_at": ctx.get("generated_at"),
            "system_readiness": ctx.get("system_readiness"),
            "source": "stored [Decision Context]" if use_stored_context else "live build_payload",
        },
        "trend_reference": {
            "kind": trend.get("kind"),
            "generated_at": trend.get("generated_at"),
            "window_size": trend.get("window_size"),
            "source": "stored [System Trend]" if use_stored_trend else "live build_system_trend",
        },
        "supporting_signals": supporting,
        "caution_flags": cflags,
        "notes": [
            "Guardrail mode is policy classification only — not a trade, not analyst output.",
            "FROZEN > CAUTION > NORMAL priority uses explicit thresholds in evaluator code.",
        ],
    }
    if include_insight_ref and insight_id:
        doc["insight_reference"] = {
            "source_task_id": insight_id,
            "kind": insight_doc.get("kind") if insight_doc else None,
        }
    elif include_insight_ref:
        doc["insight_reference"] = None
        doc["notes"].append("Optional insight reference requested but no [System Insight] task found.")

    return doc


def run(
    db_path: Path,
    *,
    use_stored_context: bool,
    use_stored_trend: bool,
    include_insight_ref: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    trend_recent: int,
    store: bool,
) -> int:
    root = repo_root()
    try:
        doc = build_guardrail_document(
            db_path,
            use_stored_context=use_stored_context,
            use_stored_trend=use_stored_trend,
            include_insight_ref=include_insight_ref,
            health_limit=health_limit,
            task_limit=task_limit,
            alert_window=alert_window,
            trend_recent=trend_recent,
        )
    except (LookupError, ValueError) as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        return 3

    out: dict[str, Any] = {"guardrail_policy": doc, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = doc["generated_at"]
        title = f"[Guardrail Policy] {now[:19]}Z"
        desc = json.dumps(doc, ensure_ascii=False, indent=2)
        conn.execute(
            """
            INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, "main", title, desc, "completed", "normal", now, now),
        )
        conn.commit()
        conn.close()
        out["stored_task_id"] = tid

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 2.11 — guardrail operating mode from context + trend",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-decision-context",
        action="store_true",
        help="Use latest [Decision Context] task instead of live build_payload",
    )
    p.add_argument(
        "--use-latest-stored-trend",
        action="store_true",
        help="Use latest [System Trend] task instead of live trend from [System Insight] rows",
    )
    p.add_argument(
        "--include-insight-reference",
        action="store_true",
        help="Attach latest [System Insight] task id when present",
    )
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument(
        "--trend-recent",
        type=int,
        default=10,
        help="When building live trend: number of [System Insight] rows (default 10)",
    )
    p.add_argument("--store", action="store_true")
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Run local FROZEN/CAUTION/NORMAL branch checks (no DB) and exit",
    )
    args = p.parse_args(argv)
    if args.self_test:
        print(json.dumps(run_local_branch_tests(), indent=2, ensure_ascii=False))
        return 0
    db = args.db or default_sqlite_path()
    return run(
        db,
        use_stored_context=args.use_latest_stored_decision_context,
        use_stored_trend=args.use_latest_stored_trend,
        include_insight_ref=args.include_insight_reference,
        health_limit=max(10, args.health_limit),
        task_limit=max(5, args.task_limit),
        alert_window=max(1, args.alert_window_days),
        trend_recent=max(1, min(100, args.trend_recent)),
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
