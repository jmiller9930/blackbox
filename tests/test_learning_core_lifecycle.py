"""Directive 4.6.3.2 Part A — learning lifecycle model, transitions, persistence, enforcement."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from _db import ensure_schema
from _paths import repo_root
from learning_core.enforcement import is_reusable
from learning_core.store import (
    count_learning_transitions,
    create_learning_record,
    get_learning_record,
    transition_learning_record,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn, repo_root())
    return conn


def test_valid_transitions_pass() -> None:
    conn = _conn()
    rid = create_learning_record(
        conn,
        source="unit_test",
        source_record_id="r1",
        content="candidate content",
    )
    rec = transition_learning_record(conn, record_id=rid, to_state="under_test", notes="start testing")
    assert rec.state == "under_test"
    rec2 = transition_learning_record(conn, record_id=rid, to_state="validated", notes="passed")
    assert rec2.state == "validated"
    assert is_reusable(rec2) is True


def test_create_allows_candidate_initial_state() -> None:
    conn = _conn()
    rid = create_learning_record(
        conn,
        source="unit_test",
        source_record_id="candidate-ok",
        content="candidate seed",
        state="candidate",
    )
    rec = get_learning_record(conn, rid)
    assert rec is not None
    assert rec.state == "candidate"


def test_create_direct_validated_is_rejected() -> None:
    conn = _conn()
    with pytest.raises(ValueError):
        create_learning_record(
            conn,
            source="unit_test",
            source_record_id="bad-validated",
            content="should fail",
            state="validated",
        )


def test_create_direct_rejected_is_rejected() -> None:
    conn = _conn()
    with pytest.raises(ValueError):
        create_learning_record(
            conn,
            source="unit_test",
            source_record_id="bad-rejected",
            content="should fail",
            state="rejected",
        )


def test_invalid_transitions_fail() -> None:
    conn = _conn()
    rid = create_learning_record(
        conn,
        source="unit_test",
        source_record_id="r2",
        content="candidate content",
    )
    with pytest.raises(ValueError):
        transition_learning_record(conn, record_id=rid, to_state="validated", notes="skip under_test")


def test_rejected_is_terminal() -> None:
    conn = _conn()
    rid = create_learning_record(
        conn,
        source="unit_test",
        source_record_id="r3",
        content="candidate content",
    )
    transition_learning_record(conn, record_id=rid, to_state="under_test", notes="start testing")
    rec = transition_learning_record(conn, record_id=rid, to_state="rejected", notes="failed")
    assert rec.state == "rejected"
    with pytest.raises(ValueError):
        transition_learning_record(conn, record_id=rid, to_state="validated", notes="should fail")
    assert is_reusable(rec) is False


def test_persistence_and_audit_trail() -> None:
    conn = _conn()
    rid = create_learning_record(
        conn,
        source="unit_test",
        source_record_id="r4",
        content="persist me",
        evidence_links=["proof://one"],
    )
    rec = get_learning_record(conn, rid)
    assert rec is not None
    assert rec.state == "candidate"
    assert rec.version == 1
    assert rec.evidence_links == ["proof://one"]
    transition_learning_record(conn, record_id=rid, to_state="under_test", notes="phase2")
    transition_learning_record(conn, record_id=rid, to_state="validated", notes="phase3")
    rec2 = get_learning_record(conn, rid)
    assert rec2 is not None
    assert rec2.version == 3
    # creation + two transitions
    assert count_learning_transitions(conn, record_id=rid) == 3
