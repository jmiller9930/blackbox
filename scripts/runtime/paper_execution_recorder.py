#!/usr/bin/env python3
"""
Phase 2.6 — Paper execution recorder (executor bridge v0).

Consumes a paper-trade ticket (live build or latest stored [Paper Trade Ticket] task)
and emits a paper-only execution record. No exchange, no Drift, no Billy.
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
from paper_trade_ticket_builder import (
    compute_paper_trade_ticket_document,
    load_latest_stored_paper_trade_ticket,
)
from simulated_action_router import (
    load_latest_stored_analyst_decision,
    load_latest_stored_simulated_action,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _simulated_action_reference(conn) -> dict | None:
    try:
        tid, sim = load_latest_stored_simulated_action(conn)
        return {
            "source_task_id": tid,
            "kind": sim.get("kind"),
            "action": sim.get("action"),
            "generated_at": sim.get("generated_at"),
        }
    except (LookupError, ValueError):
        return None


def _analyst_decision_reference(conn) -> dict | None:
    try:
        tid, ad = load_latest_stored_analyst_decision(conn)
        return {
            "source_task_id": tid,
            "kind": ad.get("kind"),
            "decision": ad.get("decision"),
            "confidence": ad.get("confidence"),
            "generated_at": ad.get("generated_at"),
        }
    except (LookupError, ValueError):
        return None


def build_paper_execution_record(
    ticket_doc: dict,
    *,
    source_paper_trade_ticket_task_id: str | None,
    simulated_action_reference: dict | None,
    analyst_decision_reference: dict | None,
) -> dict:
    ts = ticket_doc.get("ticket_status")
    flags = list(ticket_doc.get("caution_flags") or [])
    base_notes = [
        "Paper-only lifecycle; no exchange fills, prices, or confirmations.",
        "No Drift or live executor; no Billy wiring.",
    ]

    if ts == "NOT_CREATED":
        return {
            "kind": "paper_execution_record_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_ticket": ticket_doc,
            "source_paper_trade_ticket_task_id": source_paper_trade_ticket_task_id,
            "simulated_action_reference": simulated_action_reference,
            "analyst_decision_reference": analyst_decision_reference,
            "execution_status": "SKIPPED",
            "execution_record": None,
            "caution_flags": flags,
            "notes": base_notes
            + [
                "execution_status=SKIPPED: ticket_status was NOT_CREATED; no ticket to execute.",
            ],
        }

    if ts == "WATCH_ONLY":
        pt = ticket_doc.get("paper_trade_ticket") or {}
        rationale = pt.get("rationale_summary") or ""
        if not rationale:
            rationale = (ticket_doc.get("source_action") or {}).get("rationale", "")[:800]
        return {
            "kind": "paper_execution_record_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_ticket": ticket_doc,
            "source_paper_trade_ticket_task_id": source_paper_trade_ticket_task_id,
            "simulated_action_reference": simulated_action_reference,
            "analyst_decision_reference": analyst_decision_reference,
            "execution_status": "WATCHING",
            "execution_record": {
                "mode": "watch_only",
                "rationale_summary": rationale,
                "monitoring_notes": pt.get("monitoring_notes"),
            },
            "caution_flags": flags,
            "notes": base_notes
            + [
                "execution_status=WATCHING: no paper execution beyond watch status.",
            ],
        }

    if ts == "READY":
        pt = ticket_doc.get("paper_trade_ticket") or {}
        return {
            "kind": "paper_execution_record_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_ticket": ticket_doc,
            "source_paper_trade_ticket_task_id": source_paper_trade_ticket_task_id,
            "simulated_action_reference": simulated_action_reference,
            "analyst_decision_reference": analyst_decision_reference,
            "execution_status": "PAPER_EXECUTED",
            "execution_record": {
                "execution_mode": "paper",
                "market": pt.get("market"),
                "direction": pt.get("direction"),
                "simulated_entry_status": (
                    "PLACEHOLDER_NOTIONAL — paper acknowledgment only; no fill price or exchange id"
                ),
                "rationale_summary": pt.get("rationale_summary"),
                "risk_posture": pt.get("risk_posture"),
                "prerequisites_checked": list(pt.get("prerequisites") or []),
                "invalidation_conditions": list(pt.get("invalidation_conditions") or []),
                "operator_notes": list(pt.get("operator_notes") or []),
            },
            "caution_flags": flags,
            "notes": base_notes
            + [
                "execution_status=PAPER_EXECUTED: structured record only; not a live order.",
            ],
        }

    return {
        "kind": "paper_execution_record_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "source_ticket": ticket_doc,
        "source_paper_trade_ticket_task_id": source_paper_trade_ticket_task_id,
        "simulated_action_reference": simulated_action_reference,
        "analyst_decision_reference": analyst_decision_reference,
        "execution_status": "SKIPPED",
        "execution_record": None,
        "caution_flags": flags,
        "notes": base_notes + [f"Unknown ticket_status {ts!r}; defaulting to SKIPPED."],
    }


def load_latest_stored_paper_execution(conn) -> tuple[str, dict]:
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[Paper Execution]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        raise LookupError("no stored [Paper Execution] task found")
    data = json.loads(row[1])
    if data.get("kind") != "paper_execution_record_v1":
        raise ValueError("latest paper execution task is not paper_execution_record_v1")
    return row[0], data


def compute_paper_execution_record_document(
    db_path: Path,
    *,
    ticket_from_stored: bool,
    attach_sim_ref: bool,
    attach_analyst_ref: bool,
    simulated_from_stored: bool,
    use_stored_context_for_live: bool,
    sim_include_context_ref: bool,
    attach_analyst_for_ticket: bool,
    attach_decision_context_for_ticket: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    analyst_from_stored_for_live: bool,
) -> dict:
    """Build paper_execution_record_v1 without printing or persisting."""
    root = repo_root()
    source_tid: str | None = None

    if ticket_from_stored:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        try:
            source_tid, ticket_doc = load_latest_stored_paper_trade_ticket(conn)
            sim_ref = _simulated_action_reference(conn) if attach_sim_ref else None
            an_ref = _analyst_decision_reference(conn) if attach_analyst_ref else None
        finally:
            conn.close()
    else:
        ticket_doc = compute_paper_trade_ticket_document(
            db_path,
            simulated_from_stored=simulated_from_stored,
            use_stored_context_for_live=use_stored_context_for_live,
            sim_include_context_ref=sim_include_context_ref,
            attach_analyst_ref=attach_analyst_for_ticket,
            attach_decision_context_ref=attach_decision_context_for_ticket,
            health_limit=health_limit,
            task_limit=task_limit,
            alert_window=alert_window,
            analyst_from_stored_for_live=analyst_from_stored_for_live,
        )
        sim_ref = None
        an_ref = None
        if attach_sim_ref or attach_analyst_ref:
            conn = connect(db_path)
            ensure_schema(conn, root)
            seed_agents(conn)
            try:
                if attach_sim_ref:
                    sim_ref = _simulated_action_reference(conn)
                if attach_analyst_ref:
                    an_ref = _analyst_decision_reference(conn)
            finally:
                conn.close()

    return build_paper_execution_record(
        ticket_doc,
        source_paper_trade_ticket_task_id=source_tid,
        simulated_action_reference=sim_ref,
        analyst_decision_reference=an_ref,
    )


def run(
    db_path: Path,
    *,
    ticket_from_stored: bool,
    attach_sim_ref: bool,
    attach_analyst_ref: bool,
    simulated_from_stored: bool,
    use_stored_context_for_live: bool,
    sim_include_context_ref: bool,
    attach_analyst_for_ticket: bool,
    attach_decision_context_for_ticket: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    analyst_from_stored_for_live: bool,
    store: bool,
) -> int:
    root = repo_root()
    ex = compute_paper_execution_record_document(
        db_path,
        ticket_from_stored=ticket_from_stored,
        attach_sim_ref=attach_sim_ref,
        attach_analyst_ref=attach_analyst_ref,
        simulated_from_stored=simulated_from_stored,
        use_stored_context_for_live=use_stored_context_for_live,
        sim_include_context_ref=sim_include_context_ref,
        attach_analyst_for_ticket=attach_analyst_for_ticket,
        attach_decision_context_for_ticket=attach_decision_context_for_ticket,
        health_limit=health_limit,
        task_limit=task_limit,
        alert_window=alert_window,
        analyst_from_stored_for_live=analyst_from_stored_for_live,
    )

    result: dict = {"paper_execution_record": ex, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = ex["generated_at"]
        title = f"[Paper Execution] {now[:19]}Z"
        desc = json.dumps(ex, ensure_ascii=False, indent=2)
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
        description="Phase 2.6 — paper execution record from paper trade ticket",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-paper-ticket",
        action="store_true",
        help="Load latest [Paper Trade Ticket] task instead of building ticket live",
    )
    p.add_argument(
        "--attach-simulated-action-ref",
        action="store_true",
        help="Include summary of latest stored simulated action",
    )
    p.add_argument(
        "--attach-analyst-ref",
        action="store_true",
        help="Include summary of latest stored analyst decision",
    )
    p.add_argument(
        "--use-latest-stored-simulated-action",
        action="store_true",
        help="When building ticket live: use stored simulated action",
    )
    p.add_argument(
        "--use-latest-stored-analyst",
        action="store_true",
        help="When building ticket live: use stored analyst for simulated chain",
    )
    p.add_argument(
        "--use-latest-stored-context",
        action="store_true",
        help="When building ticket live: use stored decision context",
    )
    p.add_argument(
        "--sim-include-context-ref",
        action="store_true",
    )
    p.add_argument(
        "--ticket-attach-analyst-ref",
        action="store_true",
        help="When building ticket live: attach analyst ref into ticket doc",
    )
    p.add_argument(
        "--ticket-attach-decision-context-ref",
        action="store_true",
    )
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument("--store", action="store_true")
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(
        db,
        ticket_from_stored=args.use_latest_stored_paper_ticket,
        attach_sim_ref=args.attach_simulated_action_ref,
        attach_analyst_ref=args.attach_analyst_ref,
        simulated_from_stored=args.use_latest_stored_simulated_action,
        use_stored_context_for_live=args.use_latest_stored_context,
        sim_include_context_ref=args.sim_include_context_ref,
        attach_analyst_for_ticket=args.ticket_attach_analyst_ref,
        attach_decision_context_for_ticket=args.ticket_attach_decision_context_ref,
        health_limit=max(10, args.health_limit),
        task_limit=max(5, args.task_limit),
        alert_window=max(1, args.alert_window_days),
        analyst_from_stored_for_live=args.use_latest_stored_analyst,
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
