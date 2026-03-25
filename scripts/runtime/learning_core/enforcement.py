"""Reuse enforcement: only validated learning records are reusable."""

from __future__ import annotations

import sqlite3

from learning_core.models import LearningRecord
from learning_core.store import get_learning_record_by_source


def is_reusable(record: LearningRecord | None) -> bool:
    return bool(record is not None and record.state == "validated")


def is_reusable_by_source(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_record_id: str,
) -> bool:
    rec = get_learning_record_by_source(
        conn,
        source=source,
        source_record_id=source_record_id,
    )
    return is_reusable(rec)
