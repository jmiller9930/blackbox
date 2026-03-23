"""Query `system_events` for `execution_feedback_v1` payloads (no schema change)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import connect, ensure_schema
from _paths import default_sqlite_path, repo_root


def _normalize_row(event_id: str, created_at: str, payload_raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return None
    if payload.get("kind") != "execution_feedback_v1":
        return None
    insight = payload.get("insight") or {}
    outcome = payload.get("outcome") or {}
    return {
        "id": event_id,
        "created_at": created_at,
        "outcome": outcome,
        "insight": insight,
        "schema_version": payload.get("schema_version"),
    }


def fetch_insights(
    *,
    limit: int | None = 100,
    insight_kind: str | None = None,
    insight_type: str | None = None,
    request_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return recent `execution_feedback_v1` events as structured dicts.

    Filters (all optional):
    - insight_kind: e.g. execution_succeeded, blocked_not_approved
    - insight_type: \"success\" or \"failure\" (matches insight.type)
    - request_id: exact linked_request_id
    """
    root = repo_root()
    db = default_sqlite_path()
    conn = connect(db)
    ensure_schema(conn, root)
    cur = conn.execute(
        """
        SELECT id, created_at, payload FROM system_events
        WHERE source = ? AND event_type = ?
        ORDER BY created_at DESC
        """,
        ("execution_plane", "execution_feedback_v1"),
    )
    raw_rows = cur.fetchall()
    conn.close()

    out: list[dict[str, Any]] = []
    for event_id, created_at, payload_raw in raw_rows:
        row = _normalize_row(event_id, created_at, payload_raw)
        if row is None:
            continue
        ins = row.get("insight") or {}
        if insight_kind is not None and ins.get("insight_kind") != insight_kind:
            continue
        if insight_type is not None and ins.get("type") != insight_type:
            continue
        if request_id is not None and ins.get("linked_request_id") != request_id:
            continue
        out.append(row)
        if limit is not None and len(out) >= limit:
            break
    return out
