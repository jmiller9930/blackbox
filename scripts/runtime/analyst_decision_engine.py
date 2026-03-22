#!/usr/bin/env python3
"""
Phase 2.3 — Analyst prototype (decision engine v0): rule-based recommendations from
Phase 2.2 decision context. No ML, no trades, no registry agent.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root
from decision_context_builder import build_payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_latest_stored_decision_context(conn) -> dict | None:
    row = conn.execute(
        """
        SELECT description
        FROM tasks
        WHERE title LIKE '[Decision Context]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        d = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    if d.get("kind") != "decision_context_v1":
        return None
    return d


def _snapshot(ctx: dict) -> dict:
    h = ctx.get("health_summary") or {}
    return {
        "system_readiness": ctx.get("system_readiness"),
        "health_summary": {
            "latest_by_check_type": h.get("latest_by_check_type"),
            "sqlite": h.get("sqlite"),
            "gateway": h.get("gateway"),
            "ollama": h.get("ollama"),
            "recent_failure_row_count": h.get("recent_failure_row_count"),
        },
        "alert_summary": ctx.get("alert_summary"),
        "outcome_summary": ctx.get("outcome_summary"),
        "reflection_summary": {
            "latest_reflection_task_id": (ctx.get("reflection_summary") or {}).get(
                "latest_reflection_task_id"
            ),
            "latest_title": (ctx.get("reflection_summary") or {}).get("latest_title"),
        },
    }


def decide(ctx: dict, signal_stub: str | None) -> dict:
    readiness = ctx.get("system_readiness") or "unknown"
    flags = list(ctx.get("caution_flags") or [])
    alerts = ctx.get("alert_summary") or {}
    outcome = ctx.get("outcome_summary") or {}
    health = ctx.get("health_summary") or {}
    bys = outcome.get("by_status") or {}
    open_a = int(alerts.get("open_unacknowledged_count") or 0)
    fail_rows = int(health.get("recent_failure_row_count") or 0)
    succ = int(bys.get("success") or 0)
    unk = int(bys.get("unknown") or 0)
    miss = int(bys.get("missing") or 0)
    skew = (succ > 0 and (unk + miss) > succ) or (succ == 0 and (unk + miss) >= 3)

    notes: list[str] = []
    if signal_stub:
        notes.append(f"signal_stub (placeholder): {signal_stub}")

    if readiness == "unstable":
        latest = health.get("latest_by_check_type") or {}
        bad = [k for k, v in latest.items() if v == "FAIL"]
        reasoning = (
            "system unstable: latest core health snapshot shows FAIL for "
            + (", ".join(bad) if bad else "one or more components")
            + ". NO_TRADE until infrastructure is healthy."
        )
        return {
            "kind": "analyst_decision_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "decision": "NO_TRADE",
            "confidence": "low",
            "reasoning": reasoning,
            "context_snapshot": _snapshot(ctx),
            "caution_flags": flags,
            "notes": notes,
        }

    if readiness == "degraded":
        parts: list[str] = []
        if open_a > 0:
            parts.append(f"open/unacknowledged alerts={open_a}")
        if fail_rows > 0:
            parts.append(f"recent health log failures(rows)={fail_rows}")
        if skew:
            parts.append(
                f"outcome skew (success={succ}, unknown={unk}, missing={miss})"
            )
        if not parts:
            parts.append("secondary degraded signals per decision context notes")
        reasoning = (
            "REDUCED_RISK: degraded readiness — "
            + "; ".join(parts)
            + ". Reduce exposure and verify before acting."
        )
        confidence = "low" if (open_a > 2 or skew or fail_rows > 3) else "medium"
        return {
            "kind": "analyst_decision_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "decision": "REDUCED_RISK",
            "confidence": confidence,
            "reasoning": reasoning,
            "context_snapshot": _snapshot(ctx),
            "caution_flags": flags,
            "notes": notes,
        }

    if readiness == "healthy":
        reasoning = (
            "ALLOW: system_readiness healthy. Still review caution_flags and "
            "context_snapshot before any trade; no automatic execution."
        )
        notes.append(
            "Healthy path still carries operational caution_flags if listed above."
        )
        return {
            "kind": "analyst_decision_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "decision": "ALLOW",
            "confidence": "medium",
            "reasoning": reasoning,
            "context_snapshot": _snapshot(ctx),
            "caution_flags": flags,
            "notes": notes,
        }

    reasoning = f"Unknown readiness state {readiness!r}; defaulting to NO_TRADE."
    return {
        "kind": "analyst_decision_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "decision": "NO_TRADE",
        "confidence": "low",
        "reasoning": reasoning,
        "context_snapshot": _snapshot(ctx),
        "caution_flags": flags,
        "notes": notes,
    }


def run(
    db_path: Path,
    *,
    from_latest: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    signal_stub: str | None,
    store: bool,
) -> int:
    root = repo_root()
    ctx: dict | None = None
    context_source = "fresh"

    if from_latest:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        ctx = load_latest_stored_decision_context(conn)
        conn.close()
        context_source = "latest_stored_task"
        if ctx is None:
            print(
                "no stored [Decision Context] task found; run decision_context_builder.py --store first",
                file=sys.stderr,
            )
            return 3
    else:
        ctx = build_payload(db_path, health_limit, task_limit, alert_window)

    result = decide(ctx, signal_stub)
    result["context_source"] = context_source
    result["decision_context_generated_at"] = ctx.get("generated_at")

    out: dict = {"analyst_decision": result, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = result["generated_at"]
        title = f"[Analyst Decision] {result['decision']} @ {now[:19]}Z"
        desc = json.dumps(result, ensure_ascii=False, indent=2)
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
        description="Phase 2.3 — rule-based analyst decision from decision context",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--from-latest",
        action="store_true",
        help="Use latest stored [Decision Context] task instead of fresh build",
    )
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument(
        "--signal",
        default=None,
        help="Optional placeholder string (not trading logic)",
    )
    p.add_argument(
        "--store",
        action="store_true",
        help="Persist analyst output as a completed task row",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(
        db,
        from_latest=args.from_latest,
        health_limit=max(10, args.health_limit),
        task_limit=max(5, args.task_limit),
        alert_window=max(1, args.alert_window_days),
        signal_stub=args.signal,
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
