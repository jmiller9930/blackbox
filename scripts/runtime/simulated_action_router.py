#!/usr/bin/env python3
"""
Phase 2.4 — Simulated action router: analyst decision → safe action intent (no execution).

No trades, no exchanges, no executor. Optional persistence as a tasks row.
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
from analyst_decision_engine import (
    build_analyst_output,
    decide,
    load_latest_stored_decision_context,
)
from decision_context_builder import build_payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_latest_stored_analyst_decision(conn) -> tuple[str, dict]:
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[Analyst Decision]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        raise LookupError("no stored [Analyst Decision] task found")
    data = json.loads(row[1])
    if data.get("kind") != "analyst_decision_v1":
        raise ValueError("latest analyst task is not analyst_decision_v1")
    return row[0], data


def _context_reference(conn) -> dict | None:
    """Small reference blob from latest stored decision context (optional)."""
    try:
        ctx = load_latest_stored_decision_context(conn)
    except (LookupError, ValueError):
        return None
    return {
        "kind": ctx.get("kind"),
        "generated_at": ctx.get("generated_at"),
        "system_readiness": ctx.get("system_readiness"),
        "review_scope": ctx.get("review_scope"),
    }


def route_to_action(analyst: dict) -> dict:
    """Map analyst decision to simulated action fields (rule-based)."""
    dec = analyst.get("decision")
    reason = analyst.get("reasoning") or ""

    if dec == "NO_TRADE":
        return {
            "action": "HOLD",
            "rationale": (
                "Analyst decision is NO_TRADE; hold all execution. "
                f"Underlying reasoning: {reason}"
            ),
            "execution_notes": [
                "No live trade.",
                "No simulated execution proposal while decision blocks trading.",
                "Do not route to paper or live execution bridges.",
            ],
            "next_step_recommendation": "wait_for_healthier_state",
        }

    if dec == "REDUCED_RISK":
        return {
            "action": "WATCH",
            "rationale": (
                "Analyst decision is REDUCED_RISK (degraded readiness). "
                f"Align with caution_flags and analyst reasoning: {reason}"
            ),
            "execution_notes": [
                "No live trade.",
                "Monitor conditions, alerts, and outcomes; require additional confirmation before any size.",
                "Optional: paper-trade rehearsal only under explicit policy—not automatic.",
            ],
            "next_step_recommendation": "continue_monitoring",
        }

    if dec == "ALLOW":
        return {
            "action": "PAPER_TRADE_READY",
            "rationale": (
                "Analyst decision is ALLOW: readiness permits moving to **simulation** intent only. "
                "This is approval for paper/simulation readiness—not production execution. "
                f"Context: {reason}"
            ),
            "execution_notes": [
                "Simulated execution recommendation only; no real trade or exchange interaction.",
                "No Billy/executor wiring from this router in Phase 2.4.",
                "Human or future paper-trade pipeline may generate a notional ticket; capital stays zero.",
            ],
            "next_step_recommendation": "generate_paper_trade_ticket",
        }

    return {
        "action": "HOLD",
        "rationale": f"Unrecognized analyst decision {dec!r}; defaulting to HOLD. {reason}",
        "execution_notes": ["Default safe hold; review analyst output."],
        "next_step_recommendation": "request_analyst_refresh",
    }


def build_simulated_payload(
    analyst: dict,
    *,
    decision_context_reference: dict | None,
    source_task_id: str | None,
) -> dict:
    routed = route_to_action(analyst)
    out = {
        "kind": "simulated_action_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "source_decision": analyst,
        "source_analyst_task_id": source_task_id,
        "decision_context_reference": decision_context_reference,
        "action": routed["action"],
        "rationale": routed["rationale"],
        "caution_flags": analyst.get("caution_flags") or [],
        "execution_notes": routed["execution_notes"],
        "next_step_recommendation": routed["next_step_recommendation"],
    }
    # confidence passthrough for audit (optional but useful)
    return out


def load_latest_stored_simulated_action(conn) -> tuple[str, dict]:
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[Simulated Action]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        raise LookupError("no stored [Simulated Action] task found")
    data = json.loads(row[1])
    if data.get("kind") != "simulated_action_v1":
        raise ValueError("latest simulated-action task is not simulated_action_v1")
    return row[0], data


def compute_simulated_action(
    db_path: Path,
    *,
    analyst_from_stored: bool,
    use_stored_context_for_live: bool,
    include_context_ref: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
) -> tuple[dict, str | None]:
    """Build simulated_action_v1 JSON without persisting or printing."""
    root = repo_root()
    source_task_id: str | None = None
    decision_context_reference: dict | None = None

    if analyst_from_stored:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        try:
            source_task_id, analyst = load_latest_stored_analyst_decision(conn)
            if include_context_ref:
                decision_context_reference = _context_reference(conn)
        finally:
            conn.close()
    else:
        if use_stored_context_for_live:
            conn = connect(db_path)
            ensure_schema(conn, root)
            seed_agents(conn)
            try:
                ctx = load_latest_stored_decision_context(conn)
            finally:
                conn.close()
        else:
            ctx = build_payload(db_path, health_limit, task_limit, alert_window)

        block = decide(ctx)
        analyst = build_analyst_output(ctx, block)

        if include_context_ref:
            conn = connect(db_path)
            ensure_schema(conn, root)
            seed_agents(conn)
            try:
                decision_context_reference = _context_reference(conn)
            finally:
                conn.close()

    sim = build_simulated_payload(
        analyst,
        decision_context_reference=decision_context_reference,
        source_task_id=source_task_id,
    )
    return sim, source_task_id


def run(
    db_path: Path,
    *,
    analyst_from_stored: bool,
    use_stored_context_for_live: bool,
    include_context_ref: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    store: bool,
) -> int:
    root = repo_root()
    sim, _source_id = compute_simulated_action(
        db_path,
        analyst_from_stored=analyst_from_stored,
        use_stored_context_for_live=use_stored_context_for_live,
        include_context_ref=include_context_ref,
        health_limit=health_limit,
        task_limit=task_limit,
        alert_window=alert_window,
    )

    result: dict = {"simulated_action": sim, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = sim["generated_at"]
        title = f"[Simulated Action] {now[:19]}Z"
        desc = json.dumps(sim, ensure_ascii=False, indent=2)
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
        description="Phase 2.4 — simulated action intent from analyst decision",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-analyst",
        action="store_true",
        help="Load latest [Analyst Decision] task instead of computing live",
    )
    p.add_argument(
        "--use-latest-stored-context",
        action="store_true",
        help="When computing live analyst, use stored [Decision Context] task as context",
    )
    p.add_argument(
        "--include-decision-context-ref",
        action="store_true",
        help="Attach summary of latest stored [Decision Context] if present",
    )
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument("--store", action="store_true")
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(
        db,
        analyst_from_stored=args.use_latest_stored_analyst,
        use_stored_context_for_live=args.use_latest_stored_context,
        include_context_ref=args.include_decision_context_ref,
        health_limit=max(10, args.health_limit),
        task_limit=max(5, args.task_limit),
        alert_window=max(1, args.alert_window_days),
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
