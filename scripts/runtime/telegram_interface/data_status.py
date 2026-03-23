"""Read-only execution / system status text for DATA persona (no secrets)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import connect, ensure_schema
from _paths import default_sqlite_path, repo_root
from context_loader import build_output, execution_context_path, parse_context_md


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
