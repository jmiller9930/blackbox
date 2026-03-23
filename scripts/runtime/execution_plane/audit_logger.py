"""Append audit records to existing SQLite `system_events` (no schema migration)."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import connect, ensure_schema
from _paths import default_sqlite_path, repo_root

# event_type values: request_created, request_approved, request_rejected,
# execution_attempted, execution_feedback_v1 (Phase 4.4 — outcome + insight, one row per attempt).
# execution_blocked / execution_success are not emitted by run_execution (Phase 4.4+); legacy DB rows may exist.


def log_audit(event_type: str, payload: dict[str, Any]) -> None:
    root = repo_root()
    db = default_sqlite_path()
    conn = connect(db)
    ensure_schema(conn, root)
    eid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO system_events (id, source, event_type, severity, payload) VALUES (?, ?, ?, ?, ?)",
        (eid, "execution_plane", event_type, "info", json.dumps(payload, sort_keys=True)),
    )
    conn.commit()
    conn.close()
