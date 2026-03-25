"""Read-only execution / system status text for DATA persona (no secrets)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import connect, ensure_schema
from _paths import default_sqlite_path, repo_root
from context_loader import build_output, execution_context_path, parse_context_md


def get_learning_state_summary(conn=None) -> dict[str, int]:
    """
    Read-only learning record counts by lifecycle state.
    Visibility only: not used in DATA response generation yet.
    """
    own_conn = False
    if conn is None:
        own_conn = True
        conn = connect(default_sqlite_path())
        ensure_schema(conn, repo_root())
    states = ("candidate", "under_test", "validated", "rejected")
    out = {s: 0 for s in states}
    cur = conn.execute(
        "SELECT state, COUNT(*) FROM learning_records GROUP BY state"
    )
    for state, n in cur.fetchall():
        s = str(state)
        if s in out:
            out[s] = int(n)
    if own_conn:
        conn.close()
    return out


def get_recent_learning_transitions(*, limit: int = 10, conn=None) -> list[dict[str, Any]]:
    """
    Read-only transition inspection for audit visibility.
    Visibility only: not used in DATA response generation yet.
    """
    own_conn = False
    if conn is None:
        own_conn = True
        conn = connect(default_sqlite_path())
        ensure_schema(conn, repo_root())
    rows = conn.execute(
        """
        SELECT record_id, from_state, to_state, changed_at, notes
        FROM learning_record_transitions
        ORDER BY datetime(changed_at) DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "record_id": str(r[0]),
                "from_state": str(r[1]) if r[1] is not None else None,
                "to_state": str(r[2]),
                "changed_at": str(r[3]),
                "notes": str(r[4] or ""),
            }
        )
    if own_conn:
        conn.close()
    return out


def build_status_text() -> str:
    """Human-readable phase, host, proof flag, plus feedback row count."""
    lines: list[str] = []

    p = execution_context_path()
    if p.is_file():
        blob = parse_context_md(p.read_text(encoding="utf-8"))
        if "error" not in blob:
            out = build_output(blob)
            lines.extend(
                [
                    f"Current phase: {out.get('current_phase')}",
                    f"Last completed phase: {out.get('last_completed_phase')}",
                    f"Verification host: {out.get('execution_host')}",
                    f"Proof required: {out.get('proof_required')}",
                    f"Repo path (context): {out.get('repo_path')}",
                ]
            )
        else:
            lines.append(f"Execution context: {blob.get('error')}")
    else:
        lines.append("Execution context file not found.")

    root = repo_root()
    db = default_sqlite_path()
    try:
        conn = connect(db)
        ensure_schema(conn, root)
        cur = conn.execute(
            "SELECT COUNT(*) FROM system_events WHERE event_type = ?",
            ("execution_feedback_v1",),
        )
        n = int(cur.fetchone()[0])
        conn.close()
        lines.append(f"Execution feedback rows (execution_feedback_v1): {n}")
    except Exception as e:
        lines.append(f"DB status snippet unavailable: {e}")

    return "\n".join(lines)


def build_infra_snapshot() -> str:
    """
    Read-only infrastructure facts from the workspace SQLite (proves DATA has DB access on this host).
    No secrets; bounded table list + safe row counts.
    """
    lines: list[str] = []
    root = repo_root()
    db = default_sqlite_path()
    lines.append(f"SQLite path (this runtime): {db}")
    try:
        conn = connect(db)
        ensure_schema(conn, root)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cur.fetchall()]
        if not tables:
            lines.append("No user tables found (empty or unreadable).")
        else:
            lines.append(f"Tables visible here ({len(tables)}): {', '.join(tables[:30])}")
            if len(tables) > 30:
                lines.append("… (truncated)")
        for tbl in ("tasks", "system_events", "alerts", "agents", "runs"):
            if tbl in tables:
                try:
                    n = conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
                    lines.append(f"Rows · {tbl}: {int(n)}")
                except Exception as e:
                    lines.append(f"Rows · {tbl}: (unavailable: {e})")
        conn.close()
    except Exception as e:
        lines.append(f"Could not open database: {e}")
    lines.append("")
    lines.append(
        "This is the same DB the runtime uses on this machine (read-only from chat). "
        "Anna does not query it unless you route to DATA."
    )
    return "\n".join(lines)
