#!/usr/bin/env python3
"""
Phase 2.7 — Evaluate paper execution records (structure/viability only; no market/PnL).

Bounded rules: completeness, chain consistency, prerequisites/invalidate presence, caution load.
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
from paper_execution_recorder import (
    compute_paper_execution_record_document,
    load_latest_stored_paper_execution,
)
from paper_trade_ticket_builder import load_latest_stored_paper_trade_ticket
from simulated_action_router import load_latest_stored_analyst_decision


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _paper_trade_ticket_reference(conn) -> dict | None:
    try:
        tid, doc = load_latest_stored_paper_trade_ticket(conn)
        return {
            "source_task_id": tid,
            "kind": doc.get("kind"),
            "ticket_status": doc.get("ticket_status"),
        }
    except (LookupError, ValueError, json.JSONDecodeError):
        return None


def _analyst_reference(conn) -> dict | None:
    try:
        tid, ad = load_latest_stored_analyst_decision(conn)
        return {
            "source_task_id": tid,
            "kind": ad.get("kind"),
            "decision": ad.get("decision"),
            "confidence": ad.get("confidence"),
        }
    except (LookupError, ValueError, json.JSONDecodeError):
        return None


def _evaluate_paper_executed(ex: dict) -> tuple[str, str, list[str]]:
    """SUCCESS | FAILURE | UNKNOWN from structure only."""
    er = ex.get("execution_record") or {}
    flags = list(ex.get("caution_flags") or [])
    notes: list[str] = []

    if ex.get("kind") != "paper_execution_record_v1":
        return "FAILURE", "execution payload kind is not paper_execution_record_v1", notes + [
            "invalid root kind"
        ]

    if ex.get("execution_status") != "PAPER_EXECUTED":
        return "UNKNOWN", "internal branch mismatch for PAPER_EXECUTED evaluator", notes

    req_keys = (
        "execution_mode",
        "market",
        "direction",
        "simulated_entry_status",
        "rationale_summary",
        "risk_posture",
    )
    missing: list[str] = []
    for k in req_keys:
        v = er.get(k)
        if v is None or (isinstance(v, str) and not str(v).strip()):
            missing.append(k)
    if missing:
        return (
            "FAILURE",
            f"Missing or empty required execution_record fields: {missing}",
            notes + ["structural completeness check failed"],
        )

    if er.get("execution_mode") != "paper":
        return "FAILURE", "execution_mode must be 'paper' for this pipeline", notes + [
            "mode mismatch"
        ]

    st = ex.get("source_ticket") or {}
    if st.get("kind") != "paper_trade_ticket_v1":
        return "FAILURE", "source_ticket.kind is not paper_trade_ticket_v1", notes + [
            "chain break"
        ]
    sa = st.get("source_action") or {}
    if sa.get("kind") != "simulated_action_v1":
        return "FAILURE", "source_ticket.source_action.kind is not simulated_action_v1", notes + [
            "chain break"
        ]

    pre = er.get("prerequisites_checked")
    inv = er.get("invalidation_conditions")
    if not isinstance(pre, list) or not isinstance(inv, list):
        return (
            "FAILURE",
            "prerequisites_checked and invalidation_conditions must be lists",
            notes + ["type check failed"],
        )
    if len(pre) == 0 or len(inv) == 0:
        notes.append("Empty prerequisites or invalidation list — viability unclear")
        return (
            "UNKNOWN",
            "Prerequisites or invalidation lists are empty; cannot assert full viability under paper rules.",
            notes,
        )

    if len(flags) >= 3:
        notes.append("caution_flags count >= 3 — degraded confidence")
        return (
            "UNKNOWN",
            "Multiple caution flags on the execution record; outcome not confidently marked success.",
            notes,
        )

    return (
        "SUCCESS",
        "Record is structurally complete, chain kinds align (ticket → simulated action), "
        "execution_mode is paper, prerequisites and invalidation lists present, and caution load is bounded.",
        notes + ["No market/PnL used; evaluation is viability-only."],
    )


def build_outcome_document(
    ex: dict,
    *,
    source_paper_execution_task_id: str | None,
    paper_trade_ticket_reference: dict | None,
    analyst_decision_reference: dict | None,
) -> dict:
    es = ex.get("execution_status")
    flags = list(ex.get("caution_flags") or [])
    base_notes = [
        "Evaluation uses structure and chain consistency only — no PnL, fills, or exchange data.",
    ]

    if es == "SKIPPED":
        return {
            "kind": "paper_execution_outcome_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_execution": ex,
            "source_paper_execution_task_id": source_paper_execution_task_id,
            "paper_trade_ticket_reference": paper_trade_ticket_reference,
            "analyst_decision_reference": analyst_decision_reference,
            "outcome_status": "NOT_APPLICABLE",
            "rationale": "execution_status was SKIPPED; no paper execution occurred to evaluate.",
            "evaluation_notes": ["No execution path — not applicable."],
            "caution_flags": flags,
            "notes": base_notes,
        }

    if es == "WATCHING":
        return {
            "kind": "paper_execution_outcome_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_execution": ex,
            "source_paper_execution_task_id": source_paper_execution_task_id,
            "paper_trade_ticket_reference": paper_trade_ticket_reference,
            "analyst_decision_reference": analyst_decision_reference,
            "outcome_status": "MONITORING",
            "rationale": "execution_status is WATCHING; observational only — no paper execution outcome yet.",
            "evaluation_notes": ["Watch-only state remains outside SUCCESS/FAILURE/UNKNOWN trade outcome semantics."],
            "caution_flags": flags,
            "notes": base_notes,
        }

    if es == "PAPER_EXECUTED":
        ost, rat, evn = _evaluate_paper_executed(ex)
        return {
            "kind": "paper_execution_outcome_v1",
            "schema_version": 1,
            "generated_at": _utc_now(),
            "source_execution": ex,
            "source_paper_execution_task_id": source_paper_execution_task_id,
            "paper_trade_ticket_reference": paper_trade_ticket_reference,
            "analyst_decision_reference": analyst_decision_reference,
            "outcome_status": ost,
            "rationale": rat,
            "evaluation_notes": evn,
            "caution_flags": flags,
            "notes": base_notes,
        }

    return {
        "kind": "paper_execution_outcome_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "source_execution": ex,
        "source_paper_execution_task_id": source_paper_execution_task_id,
        "paper_trade_ticket_reference": paper_trade_ticket_reference,
        "analyst_decision_reference": analyst_decision_reference,
        "outcome_status": "UNKNOWN",
        "rationale": f"Unexpected execution_status {es!r}.",
        "evaluation_notes": [],
        "caution_flags": flags,
        "notes": base_notes,
    }


def run(
    db_path: Path,
    *,
    execution_from_stored: bool,
    with_ticket_summary: bool,
    with_analyst_summary: bool,
    ticket_from_stored: bool,
    attach_sim_ref: bool,
    recorder_attach_analyst: bool,
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
    source_ex_id: str | None = None

    if execution_from_stored:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        try:
            source_ex_id, ex = load_latest_stored_paper_execution(conn)
            pt_ref = _paper_trade_ticket_reference(conn) if with_ticket_summary else None
            an_ref = _analyst_reference(conn) if with_analyst_summary else None
        finally:
            conn.close()
    else:
        ex = compute_paper_execution_record_document(
            db_path,
            ticket_from_stored=ticket_from_stored,
            attach_sim_ref=attach_sim_ref,
            attach_analyst_ref=recorder_attach_analyst,
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
        pt_ref = None
        an_ref = None
        if with_ticket_summary or with_analyst_summary:
            conn = connect(db_path)
            ensure_schema(conn, root)
            seed_agents(conn)
            try:
                if with_ticket_summary:
                    pt_ref = _paper_trade_ticket_reference(conn)
                if with_analyst_summary:
                    an_ref = _analyst_reference(conn)
            finally:
                conn.close()

    doc = build_outcome_document(
        ex,
        source_paper_execution_task_id=source_ex_id,
        paper_trade_ticket_reference=pt_ref,
        analyst_decision_reference=an_ref,
    )

    result: dict = {"paper_execution_outcome": doc, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = doc["generated_at"]
        title = f"[Paper Outcome] {now[:19]}Z"
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
        description="Phase 2.7 — evaluate paper execution record outcome",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-paper-execution",
        action="store_true",
        help="Load latest [Paper Execution] task instead of computing live",
    )
    p.add_argument(
        "--with-ticket-summary",
        action="store_true",
        help="Include summary of latest stored paper trade ticket in outcome JSON",
    )
    p.add_argument(
        "--with-analyst-summary",
        action="store_true",
        help="Include summary of latest stored analyst decision in outcome JSON",
    )
    p.add_argument(
        "--use-latest-stored-paper-ticket",
        action="store_true",
        help="When computing live execution: use stored paper trade ticket",
    )
    p.add_argument(
        "--attach-simulated-action-ref",
        action="store_true",
        help="When computing live execution: attach simulated-action ref in recorder",
    )
    p.add_argument(
        "--recorder-attach-analyst",
        action="store_true",
        help="When computing live execution: attach analyst ref in recorder",
    )
    p.add_argument("--use-latest-stored-simulated-action", action="store_true")
    p.add_argument("--use-latest-stored-analyst", action="store_true")
    p.add_argument("--use-latest-stored-context", action="store_true")
    p.add_argument("--sim-include-context-ref", action="store_true")
    p.add_argument("--ticket-attach-analyst-ref", action="store_true")
    p.add_argument("--ticket-attach-decision-context-ref", action="store_true")
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument("--store", action="store_true")
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(
        db,
        execution_from_stored=args.use_latest_stored_paper_execution,
        with_ticket_summary=args.with_ticket_summary,
        with_analyst_summary=args.with_analyst_summary,
        ticket_from_stored=args.use_latest_stored_paper_ticket,
        attach_sim_ref=args.attach_simulated_action_ref,
        recorder_attach_analyst=args.recorder_attach_analyst,
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
