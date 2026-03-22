#!/usr/bin/env python3
"""
Phase 2.8 — Trade episode aggregator: link paper outcome → execution → ticket → action → analyst.

Aggregation only; no new tables, no mutation of rows, no APIs. Missing links stay null with notes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_latest_stored_paper_outcome(conn) -> tuple[str, dict]:
    row = conn.execute(
        """
        SELECT id, title, description FROM tasks
        WHERE title LIKE '[Paper Outcome]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[2]:
        raise LookupError("no stored [Paper Outcome] task found")
    data = json.loads(row[2])
    if data.get("kind") != "paper_execution_outcome_v1":
        raise ValueError("latest paper outcome task is not paper_execution_outcome_v1")
    return row[0], row[1] or "", data


def _load_task_row(conn, task_id: str) -> tuple[str, str, str, str] | None:
    row = conn.execute(
        """
        SELECT id, title, state, description FROM tasks WHERE id = ?
        """,
        (task_id,),
    ).fetchone()
    if not row:
        return None
    return row[0], row[1] or "", row[2] or "", row[3] or ""


def _parse_description(desc: str) -> dict | None:
    if not desc or not str(desc).strip():
        return None
    try:
        return json.loads(desc)
    except json.JSONDecodeError:
        return None


def _ref_note(missing: str) -> str:
    return f"No {missing}; not inferred from chain JSON."


def _episode_id(
    outcome_id: str,
    execution_id: str | None,
    ticket_id: str | None,
    sim_id: str | None,
    analyst_id: str | None,
) -> str:
    raw = "|".join(
        [
            outcome_id,
            execution_id or "",
            ticket_id or "",
            sim_id or "",
            analyst_id or "",
        ]
    )
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"ep_{h[:32]}"


def _merge_caution(*flag_lists: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for fl in flag_lists:
        for x in fl or []:
            s = str(x).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def build_trade_episode(conn) -> dict:
    notes: list[str] = [
        "Episode built from latest [Paper Outcome] and explicit task_id references only; "
        "alert/coordination task links are not inferred when absent from JSON.",
    ]

    outcome_tid, outcome_title, outcome = load_latest_stored_paper_outcome(conn)
    ex = outcome.get("source_execution") or {}
    if ex.get("kind") != "paper_execution_record_v1":
        notes.append("source_execution.kind is not paper_execution_record_v1; chain may be incomplete.")

    execution_tid = outcome.get("source_paper_execution_task_id")
    execution_doc: dict | None = None
    execution_row = None
    if execution_tid:
        execution_row = _load_task_row(conn, execution_tid)
        if execution_row:
            execution_doc = _parse_description(execution_row[3])
            if execution_doc and execution_doc.get("kind") != "paper_execution_record_v1":
                notes.append(
                    f"Stored paper execution task {execution_tid} is not paper_execution_record_v1; "
                    "using embedded source_execution from outcome."
                )
                execution_doc = None
        else:
            notes.append(f"Paper execution task id {execution_tid} not found in tasks; using embedded source_execution.")
    if execution_doc is None:
        execution_doc = ex if ex.get("kind") == "paper_execution_record_v1" else {}
    elif ex.get("kind") == "paper_execution_record_v1":
        for k in ("source_paper_trade_ticket_task_id", "source_ticket", "execution_status", "generated_at"):
            if execution_doc.get(k) is None and ex.get(k) is not None:
                execution_doc[k] = ex[k]

    ticket_tid = execution_doc.get("source_paper_trade_ticket_task_id")
    ticket_doc: dict | None = None
    ticket_row = None
    if ticket_tid:
        ticket_row = _load_task_row(conn, ticket_tid)
        if ticket_row:
            ticket_doc = _parse_description(ticket_row[3])
            if ticket_doc and ticket_doc.get("kind") != "paper_trade_ticket_v1":
                notes.append(f"Ticket task {ticket_tid} kind mismatch; using embedded source_ticket.")
                ticket_doc = None
        else:
            notes.append(f"Paper trade ticket task id {ticket_tid} not found; using embedded source_ticket.")
    if ticket_doc is None:
        st = execution_doc.get("source_ticket") or ex.get("source_ticket")
        ticket_doc = st if isinstance(st, dict) else {}

    sim_tid = None
    if isinstance(ticket_doc, dict):
        sim_tid = ticket_doc.get("source_simulated_action_task_id")
    sim_doc: dict | None = None
    sim_row = None
    if sim_tid:
        sim_row = _load_task_row(conn, sim_tid)
        if sim_row:
            sim_doc = _parse_description(sim_row[3])
            if sim_doc and sim_doc.get("kind") != "simulated_action_v1":
                notes.append(f"Simulated action task {sim_tid} kind mismatch.")
                sim_doc = None
        else:
            notes.append(f"Simulated action task id {sim_tid} not found in tasks.")
    if sim_doc is None:
        sim_doc = {}
    if (not sim_doc.get("kind")) and isinstance(ticket_doc, dict):
        sa = ticket_doc.get("source_action")
        if isinstance(sa, dict) and sa.get("kind") == "simulated_action_v1":
            sim_doc = sa
            notes.append("Using simulated action embedded under ticket.source_action; task row missing or invalid.")

    analyst_tid = None
    if isinstance(sim_doc, dict):
        analyst_tid = sim_doc.get("source_analyst_task_id")
    analyst_doc: dict | None = None
    analyst_row = None
    if analyst_tid:
        analyst_row = _load_task_row(conn, analyst_tid)
        if analyst_row:
            analyst_doc = _parse_description(analyst_row[3])
            if analyst_doc and analyst_doc.get("kind") != "analyst_decision_v1":
                notes.append(f"Analyst task {analyst_tid} kind mismatch.")
                analyst_doc = None
        else:
            notes.append(f"Analyst decision task id {analyst_tid} not found in tasks.")
    if analyst_doc is None:
        # Fall back to nested source_decision in simulated action (no task id for storage)
        analyst_doc = (sim_doc.get("source_decision") or {}) if isinstance(sim_doc.get("source_decision"), dict) else {}
        if analyst_doc.get("kind") == "analyst_decision_v1":
            notes.append("Using analyst JSON embedded in simulated action; no separate analyst task row loaded.")
        else:
            analyst_doc = {}
            notes.append("Analyst decision payload missing or unlinked.")

    # Decision context: embedded refs only (no latest-stored substitution).
    ctx_from_sim = sim_doc.get("decision_context_reference") if isinstance(sim_doc, dict) else None
    ctx_from_ticket = ticket_doc.get("decision_context_reference") if isinstance(ticket_doc, dict) else None
    decision_context_embedded: dict[str, Any] = {}
    if ctx_from_sim:
        decision_context_embedded["from_simulated_action"] = ctx_from_sim
    if ctx_from_ticket:
        decision_context_embedded["from_ticket"] = ctx_from_ticket
    if not decision_context_embedded:
        decision_context_embedded = {}
        notes.append(_ref_note("decision_context_reference blob on simulated action / ticket"))

    # Alert / coordination task: only if explicitly present in parsed JSON we already loaded.
    alert_reference: dict[str, Any] | None = None
    task_reference: dict[str, Any] | None = None
    for label, doc in (
        ("outcome", outcome),
        ("execution", execution_doc),
        ("ticket", ticket_doc),
        ("simulated_action", sim_doc),
        ("analyst", analyst_doc),
    ):
        if not isinstance(doc, dict):
            continue
        coord = doc.get("coordination")
        if isinstance(coord, dict) and coord.get("responded_to_alert_id"):
            aid = coord["responded_to_alert_id"]
            alert_reference = {
                "alert_id": aid,
                "source": label,
                "note": "Found coordination.responded_to_alert_id in loaded JSON.",
            }
            task_reference = {
                "coordination_kind": coord.get("kind"),
                "note": "Coordination block present on same document as alert reference.",
            }
            break

    if alert_reference is None:
        alert_reference = {
            "alert_id": None,
            "note": _ref_note("alert_id in pipeline task JSON"),
        }
    if task_reference is None:
        task_reference = {
            "coordination_task_id": None,
            "note": _ref_note("coordination / planning task id in pipeline JSON"),
        }

    outcome_reference = {
        "source_task_id": outcome_tid,
        "title": outcome_title or None,
        "kind": "paper_execution_outcome_v1",
        "outcome_status": outcome.get("outcome_status"),
        "generated_at": outcome.get("generated_at"),
    }

    execution_reference = {
        "source_task_id": execution_tid,
        "title": execution_row[1] if execution_row else None,
        "kind": execution_doc.get("kind") if execution_doc else None,
        "execution_status": execution_doc.get("execution_status") if execution_doc else None,
        "generated_at": execution_doc.get("generated_at") if execution_doc else None,
    }

    ticket_reference = {
        "source_task_id": ticket_tid,
        "title": ticket_row[1] if ticket_row else None,
        "kind": ticket_doc.get("kind") if ticket_doc else None,
        "ticket_status": ticket_doc.get("ticket_status") if ticket_doc else None,
        "generated_at": ticket_doc.get("generated_at") if ticket_doc else None,
    }

    action_reference = {
        "source_task_id": sim_tid,
        "title": sim_row[1] if sim_row else None,
        "kind": sim_doc.get("kind") if sim_doc else None,
        "action": sim_doc.get("action") if sim_doc else None,
        "generated_at": sim_doc.get("generated_at") if sim_doc else None,
    }

    decision_reference = {
        "source_task_id": analyst_tid,
        "title": analyst_row[1] if analyst_row else None,
        "kind": analyst_doc.get("kind") if analyst_doc else None,
        "decision": analyst_doc.get("decision") if analyst_doc else None,
        "confidence": analyst_doc.get("confidence") if analyst_doc else None,
        "generated_at": analyst_doc.get("generated_at") if analyst_doc else None,
        "context_snapshot": analyst_doc.get("context_snapshot") if analyst_doc else None,
        "decision_context_embedded": decision_context_embedded or None,
    }

    eid = _episode_id(
        outcome_tid,
        execution_tid,
        ticket_tid,
        sim_tid,
        analyst_tid,
    )

    decision_path = {
        "decision": {
            "task_id": analyst_tid,
            "decision": analyst_doc.get("decision") if analyst_doc else None,
        },
        "action": {
            "task_id": sim_tid,
            "action": sim_doc.get("action") if sim_doc else None,
        },
        "ticket": {
            "task_id": ticket_tid,
            "ticket_status": ticket_doc.get("ticket_status") if ticket_doc else None,
        },
        "execution": {
            "task_id": execution_tid,
            "execution_status": execution_doc.get("execution_status") if execution_doc else None,
        },
        "outcome": {
            "task_id": outcome_tid,
            "outcome_status": outcome.get("outcome_status"),
        },
    }

    lifecycle_summary = {
        "anchor": "latest_paper_outcome_task",
        "outcome_task_id": outcome_tid,
        "episode_id": eid,
        "ids": {
            "paper_outcome": outcome_tid,
            "paper_execution": execution_tid,
            "paper_trade_ticket": ticket_tid,
            "simulated_action": sim_tid,
            "analyst_decision": analyst_tid,
        },
        "stages_reachable": {
            "outcome": True,
            "execution": execution_tid is not None,
            "ticket": ticket_tid is not None,
            "simulated_action": sim_tid is not None,
            "analyst_decision": analyst_tid is not None or bool(analyst_doc),
        },
    }

    system_state_summary = (
        analyst_doc.get("context_snapshot")
        if isinstance(analyst_doc.get("context_snapshot"), dict)
        else None
    )

    caution_flags = _merge_caution(
        outcome.get("caution_flags"),
        ex.get("caution_flags"),
        ticket_doc.get("caution_flags") if isinstance(ticket_doc, dict) else [],
        sim_doc.get("caution_flags") if isinstance(sim_doc, dict) else [],
        analyst_doc.get("caution_flags") if isinstance(analyst_doc, dict) else [],
    )

    episode: dict[str, Any] = {
        "kind": "trade_episode_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "episode_id": eid,
        "alert_reference": alert_reference,
        "task_reference": task_reference,
        "decision_reference": decision_reference,
        "action_reference": action_reference,
        "ticket_reference": ticket_reference,
        "execution_reference": execution_reference,
        "outcome_reference": outcome_reference,
        "lifecycle_summary": lifecycle_summary,
        "decision_path": decision_path,
        "system_state_summary": system_state_summary,
        "caution_flags": caution_flags,
        "notes": notes,
    }
    return episode


def run(db_path: Path, *, store: bool) -> int:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)
    try:
        episode = build_trade_episode(conn)
    except LookupError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        return 3
    finally:
        conn.close()

    out: dict[str, Any] = {"trade_episode": episode, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = episode["generated_at"]
        title = f"[Trade Episode] {now[:19]}Z"
        desc = json.dumps(episode, ensure_ascii=False, indent=2)
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
        description="Phase 2.8 — aggregate trade episode from latest [Paper Outcome]",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--store",
        action="store_true",
        help="Persist trade_episode_v1 as a completed [Trade Episode] task",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(db, store=args.store)


if __name__ == "__main__":
    raise SystemExit(main())
