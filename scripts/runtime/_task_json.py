"""Load/merge JSON in tasks.description (Phase 2.0 outcome recording)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def load_description_json(conn: sqlite3.Connection, task_id: str) -> tuple[dict[str, Any], str]:
    row = conn.execute(
        "SELECT description FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    if not row or row[0] is None:
        raise LookupError(f"task not found or empty description: {task_id}")
    raw = row[0]
    if not str(raw).strip():
        raise ValueError(f"task {task_id} has empty description")
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError as e:
        raise ValueError(f"task {task_id} description is not valid JSON: {e}") from e


def save_description_json(
    conn: sqlite3.Connection,
    task_id: str,
    payload: dict[str, Any],
    updated_at: str,
) -> None:
    conn.execute(
        """
        UPDATE tasks SET description = ?, updated_at = ? WHERE id = ?
        """,
        (json.dumps(payload, ensure_ascii=False, indent=2), updated_at, task_id),
    )


def merge_outcome(
    payload: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Merge outcome block; preserve coordination and all other keys."""
    out = dict(payload)
    out["outcome"] = outcome
    return out
