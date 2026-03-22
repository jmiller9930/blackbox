#!/usr/bin/env python3
"""
Phase 2.2 — Decision context builder: package health + tasks + outcomes + reflections
into one JSON payload for future Analyst use. Rule-based readiness; no ML; no trades.
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


CORE_CHECKS = ("sqlite", "gateway", "ollama")


def _parse_task_outcome(desc: str | None) -> tuple[str | None, bool]:
    """Return (outcome_status, has_coordination)."""
    if not desc or not str(desc).strip():
        return None, False
    try:
        d = json.loads(desc)
    except json.JSONDecodeError:
        return None, False
    out = d.get("outcome") if isinstance(d, dict) else None
    ost = out.get("status") if isinstance(out, dict) else None
    coord = d.get("coordination") if isinstance(d, dict) else None
    has_c = bool(
        isinstance(coord, dict) and coord.get("responded_to_alert_id")
    )
    return (ost if ost in ("success", "failure", "unknown") else None), has_c


def _gather_health(conn, limit: int) -> tuple[dict, list[tuple]]:
    rows = conn.execute(
        """
        SELECT id, checked_at, target, check_type, status, summary
        FROM system_health_logs
        ORDER BY datetime(checked_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    latest: dict[str, str] = {}
    for _id, _ca, _tg, ctype, st, _sm in rows:
        if ctype in CORE_CHECKS and ctype not in latest:
            latest[ctype] = st

    fail_n = sum(1 for r in rows if r[4] == "FAIL")
    return (
        {
            "rows_examined": len(rows),
            "latest_by_check_type": latest,
            "recent_failure_row_count": fail_n,
            "sqlite": latest.get("sqlite"),
            "gateway": latest.get("gateway"),
            "ollama": latest.get("ollama"),
        },
        rows,
    )


def _gather_alerts(conn, window_days: int) -> dict:
    row = conn.execute(
        f"""
        SELECT COUNT(*) FROM alerts
        WHERE datetime(created_at) >= datetime('now', '-{int(window_days)} days')
        """
    ).fetchone()
    total_window = int(row[0]) if row else 0

    open_unacked = conn.execute(
        """
        SELECT COUNT(*) FROM alerts
        WHERE acknowledged_at IS NULL
          AND (status IS NULL OR TRIM(LOWER(status)) = 'open')
        """
    ).fetchone()[0]

    return {
        "alerts_in_window_days": total_window,
        "window_days": window_days,
        "open_unacknowledged_count": int(open_unacked),
    }


def _gather_tasks(conn, limit: int) -> tuple[dict, list]:
    rows = conn.execute(
        """
        SELECT id, title, description, state, created_at, updated_at
        FROM tasks
        WHERE title IS NULL
           OR (title NOT LIKE '[Reflection]%' AND title NOT LIKE '[Decision Context]%')
        ORDER BY datetime(updated_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    states: dict[str, int] = {}
    outcome_counts = {"success": 0, "failure": 0, "unknown": 0, "missing": 0}
    coord_linked: list[dict] = []

    for tid, title, desc, state, _ca, _ua in rows:
        states[state or ""] = states.get(state or "", 0) + 1
        ost, has_c = _parse_task_outcome(desc)
        if ost == "success":
            outcome_counts["success"] += 1
        elif ost == "failure":
            outcome_counts["failure"] += 1
        elif ost == "unknown":
            outcome_counts["unknown"] += 1
        else:
            outcome_counts["missing"] += 1
        if has_c:
            coord_linked.append(
                {"task_id": tid, "title": (title or "")[:120], "state": state}
            )

    task_summary = {
        "operational_tasks_examined": len(rows),
        "count_by_state": states,
        "coordination_linked_recent": coord_linked[:15],
    }
    return task_summary, outcome_counts


def _gather_reflection(conn) -> dict:
    row = conn.execute(
        """
        SELECT id, title, description, updated_at
        FROM tasks
        WHERE title LIKE '[Reflection]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()

    if not row:
        return {
            "latest_reflection_task_id": None,
            "latest_title": None,
            "recommended_improvements": [],
            "confidence_notes": None,
        }

    tid, title, desc, _ua = row
    rec: list = []
    conf: str | None = None
    if desc and str(desc).strip():
        try:
            d = json.loads(desc)
            rec = d.get("recommended_improvements") or []
            conf = d.get("confidence_notes")
            if not rec and "reflection" in d:
                rec = (d.get("reflection") or {}).get("recommended_improvements") or []
        except json.JSONDecodeError:
            pass

    return {
        "latest_reflection_task_id": tid,
        "latest_title": title,
        "recommended_improvements": rec if isinstance(rec, list) else [],
        "confidence_notes": conf,
    }


def _readiness_and_flags(
    health: dict,
    alert_s: dict,
    outcome_counts: dict,
) -> tuple[str, list[str], list[str]]:
    """
    Rule-based, explainable classification.
    - unstable: any core component (sqlite/gateway/ollama) latest != PASS
    - degraded: cores pass but failures in window, or open alerts, or unknowns dominate
    - healthy: otherwise
    """
    latest = health.get("latest_by_check_type") or {}
    flags: list[str] = []
    notes: list[str] = []

    missing = [c for c in CORE_CHECKS if c not in latest]
    fails = [c for c in CORE_CHECKS if latest.get(c) == "FAIL"]

    if fails:
        for c in fails:
            if c == "ollama":
                flags.append("Ollama unavailable in recent checks.")
            elif c == "gateway":
                flags.append("Gateway unhealthy in recent checks.")
            elif c == "sqlite":
                flags.append("SQLite health check failed in recent logs.")
            else:
                flags.append(f"Core health check '{c}' reported FAIL in latest snapshot.")
        notes.append("Readiness=unstable: at least one core check (sqlite/gateway/ollama) is FAIL.")

    if missing and not fails:
        for c in missing:
            flags.append(f"No recent health row for '{c}' in examined window.")
        notes.append("Some core components missing from recent health logs.")

    open_alerts = alert_s.get("open_unacknowledged_count", 0)
    if open_alerts > 0:
        flags.append(
            f"{open_alerts} alert(s) remain open/unacknowledged."
        )

    unk = outcome_counts.get("unknown", 0) + outcome_counts.get("missing", 0)
    succ = outcome_counts.get("success", 0)
    if succ > 0 and unk > succ:
        flags.append("Recent unknown or missing outcomes exceed recorded successes.")
    elif succ == 0 and unk >= 3:
        flags.append("Several tasks lack a recorded outcome (success/failure/unknown).")

    # Classify: any core FAIL → unstable
    if fails:
        return "unstable", flags, notes

    if open_alerts > 2:
        notes.append("Multiple recent alerts remain unresolved (threshold >2).")
        flags.append("Multiple recent alerts remain unresolved.")

    skew = (succ > 0 and unk > succ) or (succ == 0 and unk >= 3)
    degraded_reason = (
        health.get("recent_failure_row_count", 0) > 0
        or open_alerts > 0
        or skew
        or missing
    )

    if degraded_reason:
        if not any("unstable" in n for n in notes):
            notes.append(
                "Readiness=degraded: secondary signals (failures in window, alerts, or outcome skew)."
            )
        return "degraded", flags, notes

    notes.append(
        "Readiness=healthy: core checks PASS, no open-alert pressure in ruleset, outcomes not skewed unknown."
    )
    return "healthy", flags, notes


def build_payload(
    db_path: Path,
    health_limit: int,
    task_limit: int,
    alert_window_days: int,
) -> dict:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)

    health_summary, _hrows = _gather_health(conn, health_limit)
    alert_summary = _gather_alerts(conn, alert_window_days)
    task_summary, outcome_counts = _gather_tasks(conn, task_limit)
    reflection_summary = _gather_reflection(conn)

    readiness, caution_flags, internal_notes = _readiness_and_flags(
        health_summary,
        alert_summary,
        outcome_counts,
    )
    caution_flags = list(dict.fromkeys(caution_flags))

    review_scope = {
        "health_row_limit": health_limit,
        "operational_task_limit": task_limit,
        "alert_window_days": alert_window_days,
        "database": str(db_path),
    }

    payload = {
        "kind": "decision_context_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "review_scope": review_scope,
        "health_summary": health_summary,
        "alert_summary": alert_summary,
        "task_summary": task_summary,
        "outcome_summary": {
            "by_status": outcome_counts,
            "totals": sum(outcome_counts.values()),
        },
        "reflection_summary": reflection_summary,
        "system_readiness": readiness,
        "caution_flags": caution_flags,
        "notes": internal_notes,
    }
    conn.close()
    return payload


def run(db_path: Path, store: bool, health_limit: int, task_limit: int, alert_window: int) -> int:
    payload = build_payload(db_path, health_limit, task_limit, alert_window)
    out: dict = {"decision_context": payload, "stored_task_id": None}

    if store:
        root = repo_root()
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = payload["generated_at"]
        title = f"[Decision Context] {now[:19]}Z"
        desc = json.dumps(payload, ensure_ascii=False, indent=2)
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
        description="Phase 2.2 — build decision context JSON from SQLite evidence",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument(
        "--store",
        action="store_true",
        help="Persist payload as a completed task row",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(
        db,
        args.store,
        max(10, args.health_limit),
        max(5, args.task_limit),
        max(1, args.alert_window_days),
    )


if __name__ == "__main__":
    raise SystemExit(main())
