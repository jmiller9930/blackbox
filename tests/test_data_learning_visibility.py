"""4.6.3.2 Part B step 1 — DATA read-only learning visibility helpers."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from _db import ensure_schema
from _paths import repo_root
from learning_core.store import create_learning_record, transition_learning_record
from telegram_interface.data_status import (
    get_learning_state_summary,
    get_recent_learning_transitions,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn, repo_root())
    return conn


def test_learning_state_summary_counts_states() -> None:
    conn = _conn()
    rid = create_learning_record(
        conn,
        source="unit_test",
        source_record_id="s1",
        content="c1",
    )
    transition_learning_record(conn, record_id=rid, to_state="under_test", notes="u1")
    create_learning_record(
        conn,
        source="unit_test",
        source_record_id="s2",
        content="c2",
    )
    rid3 = create_learning_record(
        conn,
        source="unit_test",
        source_record_id="s3",
        content="c3",
    )
    transition_learning_record(conn, record_id=rid3, to_state="under_test", notes="u3")
    transition_learning_record(conn, record_id=rid3, to_state="rejected", notes="r3")

    summary = get_learning_state_summary(conn)
    assert summary == {
        "candidate": 1,
        "under_test": 1,
        "validated": 0,
        "rejected": 1,
    }


def test_recent_learning_transitions_returns_ordered_rows() -> None:
    conn = _conn()
    rid = create_learning_record(
        conn,
        source="unit_test",
        source_record_id="x1",
        content="cx",
    )
    transition_learning_record(conn, record_id=rid, to_state="under_test", notes="to_test")
    transition_learning_record(conn, record_id=rid, to_state="validated", notes="to_valid")

    rows = get_recent_learning_transitions(limit=3, conn=conn)
    assert len(rows) == 3
    assert rows[0]["to_state"] == "validated"
    assert rows[1]["to_state"] == "under_test"
    assert rows[2]["to_state"] == "candidate"
