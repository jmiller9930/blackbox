#!/usr/bin/env python3
"""
Phase 2.5 — Paper-trade ticket builder from simulated action (no execution, no exchange).

Produces normalized proposal objects only; placeholders where pipeline lacks market/signal data.
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
from analyst_decision_engine import load_latest_stored_decision_context
from simulated_action_router import (
    compute_simulated_action,
    load_latest_stored_analyst_decision,
    load_latest_stored_simulated_action,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _analyst_reference(conn) -> dict | None:
    try:
        _tid, ad = load_latest_stored_analyst_decision(conn)
        return {
            "kind": ad.get("kind"),
            "generated_at": ad.get("generated_at"),
            "decision": ad.get("decision"),
            "confidence": ad.get("confidence"),
        }
    except (LookupError, ValueError):
        return None


def _context_reference(conn) -> dict | None:
    try:
        ctx = load_latest_stored_decision_context(conn)
    except (LookupError, ValueError):
        return None
    return {
        "kind": ctx.get("kind"),
        "generated_at": ctx.get("generated_at"),
        "system_readiness": ctx.get("system_readiness"),
    }


def build_paper_ticket(
    sim: dict,
    *,
    source_simulated_action_task_id: str | None,
    analyst_ref: dict | None,
    context_ref: dict | None,
) -> dict:
    action = sim.get("action")
    flags = list(sim.get("caution_flags") or [])
    base_notes = [
        "No live market data invented; placeholders used where pipeline is silent.",
        "Simulation only — zero exchange or executor interaction from this script.",
    ]

    if action == "HOLD":
        return {
            "kind": "paper_trade_ticket_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_action": sim,
            "source_simulated_action_task_id": source_simulated_action_task_id,
            "analyst_decision_reference": analyst_ref,
            "decision_context_reference": context_ref,
            "ticket_status": "NOT_CREATED",
            "paper_trade_ticket": None,
            "caution_flags": flags,
            "notes": base_notes
            + [
                "ticket_status=NOT_CREATED: simulated action is HOLD; no trade action permitted.",
            ],
        }

    if action == "WATCH":
        return {
            "kind": "paper_trade_ticket_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_action": sim,
            "source_simulated_action_task_id": source_simulated_action_task_id,
            "analyst_decision_reference": analyst_ref,
            "decision_context_reference": context_ref,
            "ticket_status": "WATCH_ONLY",
            "paper_trade_ticket": {
                "mode": "watch_only",
                "no_entry": True,
                "monitoring_notes": list(sim.get("execution_notes") or []),
                "rationale_summary": (sim.get("rationale") or "")[:800],
            },
            "caution_flags": flags,
            "notes": base_notes
            + [
                "ticket_status=WATCH_ONLY: monitor conditions; no paper entry object until readiness improves.",
            ],
        }

    if action == "PAPER_TRADE_READY":
        src = sim.get("source_decision") or {}
        conf = src.get("confidence") or "medium"
        risk = "conservative" if conf == "low" else "moderate" if conf == "medium" else "controlled"

        ticket_body = {
            "market": "PLACEHOLDER — no market feed wired in Phase 2.5",
            "direction": "PLACEHOLDER — not supplied by analyst/simulated-action chain",
            "execution_mode": "paper",
            "rationale_summary": (sim.get("rationale") or "")[:1200],
            "risk_posture": risk,
            "prerequisites": [
                "Operator acknowledges this is a notional paper ticket only.",
                "System readiness and caution_flags reviewed before any downstream simulator.",
            ],
            "invalidation_conditions": [
                "Analyst or simulated action flips to HOLD or WATCH.",
                "system_readiness degrades to unstable or decision context shows new critical alerts.",
            ],
            "operator_notes": list(sim.get("execution_notes") or [])
            + [
                "Fields marked PLACEHOLDER must be filled by future signal/market wiring — do not infer live prices here.",
            ],
        }

        return {
            "kind": "paper_trade_ticket_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_action": sim,
            "source_simulated_action_task_id": source_simulated_action_task_id,
            "analyst_decision_reference": analyst_ref,
            "decision_context_reference": context_ref,
            "ticket_status": "READY",
            "paper_trade_ticket": ticket_body,
            "caution_flags": flags,
            "notes": base_notes
            + [
                "ticket_status=READY: normalized paper proposal only; not a live order.",
            ],
        }

    return {
        "kind": "paper_trade_ticket_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "source_action": sim,
        "source_simulated_action_task_id": source_simulated_action_task_id,
        "analyst_decision_reference": analyst_ref,
        "decision_context_reference": context_ref,
        "ticket_status": "NOT_CREATED",
        "paper_trade_ticket": None,
        "caution_flags": flags,
        "notes": base_notes + [f"Unknown action {action!r}; defaulting to NOT_CREATED."],
    }


def run(
    db_path: Path,
    *,
    simulated_from_stored: bool,
    use_stored_context_for_live: bool,
    sim_include_context_ref: bool,
    attach_analyst_ref: bool,
    attach_decision_context_ref: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    analyst_from_stored_for_live: bool,
    store: bool,
) -> int:
    root = repo_root()
    source_sim_task_id: str | None = None
    analyst_ref: dict | None = None
    context_ref: dict | None = None

    if simulated_from_stored:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        try:
            source_sim_task_id, sim = load_latest_stored_simulated_action(conn)
            if attach_analyst_ref:
                analyst_ref = _analyst_reference(conn)
            if attach_decision_context_ref:
                context_ref = _context_reference(conn)
        finally:
            conn.close()
    else:
        sim, _aid = compute_simulated_action(
            db_path,
            analyst_from_stored=analyst_from_stored_for_live,
            use_stored_context_for_live=use_stored_context_for_live,
            include_context_ref=sim_include_context_ref,
            health_limit=health_limit,
            task_limit=task_limit,
            alert_window=alert_window,
        )
        if attach_analyst_ref or attach_decision_context_ref:
            conn = connect(db_path)
            ensure_schema(conn, root)
            seed_agents(conn)
            try:
                if attach_analyst_ref:
                    analyst_ref = _analyst_reference(conn)
                if attach_decision_context_ref:
                    context_ref = _context_reference(conn)
            finally:
                conn.close()

    doc = build_paper_ticket(
        sim,
        source_simulated_action_task_id=source_sim_task_id,
        analyst_ref=analyst_ref,
        context_ref=context_ref,
    )

    result: dict = {"paper_trade_ticket_document": doc, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = doc["generated_at"]
        title = f"[Paper Trade Ticket] {now[:19]}Z"
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
        result["stored_task_id"] = tid

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 2.5 — paper-trade ticket from simulated action",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-simulated-action",
        action="store_true",
        help="Load latest [Simulated Action] task instead of computing live",
    )
    p.add_argument(
        "--use-latest-stored-analyst",
        action="store_true",
        help="When computing live simulated action, use stored [Analyst Decision]",
    )
    p.add_argument(
        "--use-latest-stored-context",
        action="store_true",
        help="When computing live simulated action, use stored [Decision Context]",
    )
    p.add_argument(
        "--sim-include-context-ref",
        action="store_true",
        help="When computing live simulated action, attach stored decision context ref",
    )
    p.add_argument(
        "--attach-analyst-ref",
        action="store_true",
        help="Include latest stored analyst summary in ticket document",
    )
    p.add_argument(
        "--attach-decision-context-ref",
        action="store_true",
        help="Include latest stored decision context summary in ticket document",
    )
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument("--store", action="store_true")
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(
        db,
        simulated_from_stored=args.use_latest_stored_simulated_action,
        use_stored_context_for_live=args.use_latest_stored_context,
        sim_include_context_ref=args.sim_include_context_ref,
        attach_analyst_ref=args.attach_analyst_ref,
        attach_decision_context_ref=args.attach_decision_context_ref,
        health_limit=max(10, args.health_limit),
        task_limit=max(5, args.task_limit),
        alert_window=max(1, args.alert_window_days),
        analyst_from_stored_for_live=args.use_latest_stored_analyst,
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
