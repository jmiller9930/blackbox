"""SQLite persistence and audit trail for learning records."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from learning_core.lifecycle import assert_valid_transition
from learning_core.models import LearningRecord

_VALID_STATES = {"candidate", "under_test", "validated", "rejected"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_learning_record(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_record_id: str | None,
    content: str,
    evidence_links: list[str] | None = None,
    validation_notes: str = "",
    state: str = "candidate",
) -> str:
    if state not in _VALID_STATES:
        raise ValueError(f"invalid learning state: {state}")
    rid = str(uuid.uuid4())
    now = _utc_now()
    evidence = json.dumps(list(evidence_links or []), ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO learning_records (
          id, state, source, source_record_id, content, created_at, updated_at,
          evidence_links_json, validation_notes, version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (rid, state, source, source_record_id, content, now, now, evidence, validation_notes, 1),
    )
    conn.execute(
        """
        INSERT INTO learning_record_transitions (record_id, from_state, to_state, changed_at, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (rid, None, state, now, "created"),
    )
    conn.commit()
    return rid


def get_learning_record(conn: sqlite3.Connection, record_id: str) -> LearningRecord | None:
    row = conn.execute(
        """
        SELECT id, state, source, content, created_at, updated_at, evidence_links_json, validation_notes, version
        FROM learning_records
        WHERE id = ?
        """,
        (record_id,),
    ).fetchone()
    if not row:
        return None
    data: dict[str, Any] = {
        "id": row[0],
        "state": row[1],
        "source": row[2],
        "content": row[3],
        "created_at": row[4],
        "updated_at": row[5],
        "evidence_links": json.loads(row[6] or "[]"),
        "validation_notes": row[7] or "",
        "version": row[8] or 1,
    }
    return LearningRecord.from_row(data)


def get_learning_record_by_source(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_record_id: str,
) -> LearningRecord | None:
    row = conn.execute(
        """
        SELECT id FROM learning_records
        WHERE source = ? AND source_record_id = ?
        LIMIT 1
        """,
        (source, source_record_id),
    ).fetchone()
    if not row:
        return None
    return get_learning_record(conn, str(row[0]))


def transition_learning_record(
    conn: sqlite3.Connection,
    *,
    record_id: str,
    to_state: str,
    notes: str = "",
) -> LearningRecord:
    rec = get_learning_record(conn, record_id)
    if rec is None:
        raise LookupError(f"learning record not found: {record_id}")
    assert_valid_transition(rec.state, to_state)
    now = _utc_now()
    next_version = rec.version + 1
    conn.execute(
        """
        UPDATE learning_records
        SET state = ?, updated_at = ?, validation_notes = ?, version = ?
        WHERE id = ?
        """,
        (to_state, now, notes, next_version, record_id),
    )
    conn.execute(
        """
        INSERT INTO learning_record_transitions (record_id, from_state, to_state, changed_at, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (record_id, rec.state, to_state, now, notes),
    )
    conn.commit()
    updated = get_learning_record(conn, record_id)
    assert updated is not None
    return updated


def count_learning_transitions(conn: sqlite3.Connection, *, record_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(1) FROM learning_record_transitions WHERE record_id = ?",
        (record_id,),
    ).fetchone()
    return int((row[0] if row else 0) or 0)
