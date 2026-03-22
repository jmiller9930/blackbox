#!/usr/bin/env python3
"""
Phase 2.3 — Analyst prototype (decision engine v0).

Consumes Phase 2.2 decision context (fresh build or latest stored [Decision Context] task).
Rule-based only: NO_TRADE / REDUCED_RISK / ALLOW. No ML, no trades, no API calls.
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


def load_latest_stored_decision_context(conn) -> dict:
    row = conn.execute(
        """
        SELECT description FROM tasks
        WHERE title LIKE '[Decision Context]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[0]:
        raise LookupError("no stored [Decision Context] task found")
    data = json.loads(row[0])
    if data.get("kind") != "decision_context_v1":
        raise ValueError("latest context task is not decision_context_v1")
    return data


def _context_snapshot(ctx: dict) -> dict:
    hs = ctx.get("health_summary") or {}
    return {
        "system_readiness": ctx.get("system_readiness"),
        "health_latest": hs.get("latest_by_check_type"),
        "recent_health_fail_rows": hs.get("recent_failure_row_count"),
        "alert_open_unacknowledged": (ctx.get("alert_summary") or {}).get(
            "open_unacknowledged_count"
        ),
        "outcomes_by_status": (ctx.get("outcome_summary") or {}).get("by_status"),
        "reflection_title": (ctx.get("reflection_summary") or {}).get("latest_title"),
    }


def _degraded_confidence(ctx: dict) -> str:
    al = (ctx.get("alert_summary") or {}).get("open_unacknowledged_count") or 0
    rf = (ctx.get("health_summary") or {}).get("recent_failure_row_count") or 0
    if al > 2 or rf > 5:
        return "low"
    return "medium"


def _degraded_reasoning(ctx: dict) -> str:
    parts: list[str] = []
    hs = ctx.get("health_summary") or {}
    if hs.get("recent_failure_row_count", 0) > 0:
        parts.append(
            f"Health logs include {hs['recent_failure_row_count']} recent FAIL row(s)."
        )
    al = (ctx.get("alert_summary") or {}).get("open_unacknowledged_count") or 0
    if al > 0:
        parts.append(f"{al} open/unacknowledged alert(s).")
    bys = (ctx.get("outcome_summary") or {}).get("by_status") or {}
    unk = (bys.get("unknown") or 0) + (bys.get("missing") or 0)
    succ = bys.get("success") or 0
    if succ > 0 and unk > succ:
        parts.append("Outcome records skew toward unknown/missing vs successes.")
    elif succ == 0 and unk >= 3:
        parts.append("Few tasks have recorded outcomes (success/failure/unknown).")
    if not parts:
        parts.append(
            "Secondary signals (degraded readiness) without a single dominant trigger; see caution_flags."
        )
    return " ".join(parts)


def decide(ctx: dict) -> dict:
    readiness = ctx.get("system_readiness")
    flags = list(ctx.get("caution_flags") or [])
    ctx_notes = ctx.get("notes") or []

    if readiness == "unstable":
        return {
            "decision": "NO_TRADE",
            "confidence": "low",
            "reasoning": (
                "system_readiness is unstable: core infrastructure health (sqlite/gateway/ollama) "
                "shows FAIL in the latest snapshot. Do not trade until checks pass."
            ),
        }

    if readiness == "degraded":
        conf = _degraded_confidence(ctx)
        return {
            "decision": "REDUCED_RISK",
            "confidence": conf,
            "reasoning": _degraded_reasoning(ctx),
        }

    if readiness == "healthy":
        return {
            "decision": "ALLOW",
            "confidence": "medium",
            "reasoning": (
                "system_readiness is healthy: core checks PASS, no open-alert pressure under "
                "current rules. Operational allowance only; still review caution_flags and "
                "reflection before any real execution."
            ),
        }

    return {
        "decision": "NO_TRADE",
        "confidence": "low",
        "reasoning": f"Unknown system_readiness value {readiness!r}; defaulting to NO_TRADE.",
    }


def build_analyst_output(ctx: dict, decision_block: dict) -> dict:
    return {
        "kind": "analyst_decision_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "decision": decision_block["decision"],
        "confidence": decision_block["confidence"],
        "reasoning": decision_block["reasoning"],
        "context_snapshot": _context_snapshot(ctx),
        "caution_flags": ctx.get("caution_flags") or [],
        "notes": list(ctx.get("notes") or []),
        "signal_input": {
            "stub": True,
            "note": "No trading signal wired in Phase 2.3; placeholder for future inputs.",
        },
    }


def run(
    db_path: Path,
    *,
    use_stored_context: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    store: bool,
) -> int:
    root = repo_root()
    if use_stored_context:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        try:
            ctx = load_latest_stored_decision_context(conn)
        finally:
            conn.close()
    else:
        ctx = build_payload(db_path, health_limit, task_limit, alert_window)

    decision_block = decide(ctx)
    out_doc = build_analyst_output(ctx, decision_block)

    result: dict = {"analyst_decision": out_doc, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = out_doc["generated_at"]
        title = f"[Analyst Decision] {now[:19]}Z"
        desc = json.dumps(out_doc, ensure_ascii=False, indent=2)
        conn.execute(
            """
            INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, "main", title, desc, "completed", "normal", now, now),
        )
        conn.commit()
        conn.close()
        result["stored_task_id"] = tid

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 2.3 — rule-based analyst decision from decision context",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-context",
        action="store_true",
        help="Load latest [Decision Context] task JSON instead of rebuilding",
    )
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument(
        "--store",
        action="store_true",
        help="Persist analyst JSON as a completed task row",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(
        db,
        use_stored_context=args.use_latest_stored_context,
        health_limit=max(10, args.health_limit),
        task_limit=max(5, args.task_limit),
        alert_window=max(1, args.alert_window_days),
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
