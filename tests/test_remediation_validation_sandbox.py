"""Directive 4.6.3.2 Part B Twig 4.1 — sandbox validation engine tests."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from _paths import default_sqlite_path
from learning_core.remediation_validation import (
    create_candidate,
    get_candidate,
    open_validation_sandbox,
    run_validation,
)


def test_candidate_creation_and_readback(tmp_path: Path) -> None:
    db = tmp_path / "sandbox" / "validation.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="fix database lock contention",
        proposed_action="Suggestion only: tune transaction batching",
        evidence=["issue:db_lock_signals=3"],
    )
    rec = get_candidate(conn, rid)
    assert rec is not None
    assert rec.lifecycle_state == "candidate"
    assert rec.source == "deterministic"
    assert rec.source_type == "deterministic"
    assert "db_lock_signals" in " ".join(rec.evidence)


def test_validation_runner_records_pass_and_promotes_validated(tmp_path: Path) -> None:
    db = tmp_path / "sandbox" / "validation.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="reduce transient connectivity errors",
        proposed_action="Suggestion only: adjust retry backoff",
    )
    result = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 5, "metric_score": 0.75},
        after_state={"error_count": 1, "metric_score": 0.80, "regression_detected": False, "stable_window": True},
    )
    assert result["result"] == "pass"
    row = conn.execute("SELECT COUNT(*) FROM validation_runs WHERE remediation_id = ?", (rid,)).fetchone()
    assert int(row[0]) == 1
    rec = get_candidate(conn, rid)
    assert rec is not None
    assert rec.lifecycle_state == "validated"


def test_validation_runner_records_fail_and_marks_rejected(tmp_path: Path) -> None:
    db = tmp_path / "sandbox" / "validation.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="llm",
        description="candidate fix from optional LLM",
        proposed_action="Suggestion only: restart service",
        evidence=["llm trace id 9"],
    )
    result = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 3, "metric_score": 0.9},
        after_state={"error_count": 3, "metric_score": 0.85, "regression_detected": True, "stable_window": False},
    )
    assert result["result"] == "fail"
    assert result["failure_class"] in {"functional", "regression", "stability"}
    rec = get_candidate(conn, rid)
    assert rec is not None
    assert rec.lifecycle_state == "rejected"


def test_sandbox_rejects_production_runtime_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"
    monkeypatch.setenv("BLACKBOX_SQLITE_PATH", str(prod))
    with pytest.raises(ValueError):
        open_validation_sandbox(default_sqlite_path())


def test_sandbox_does_not_mutate_separate_production_db(tmp_path: Path) -> None:
    prod_path = tmp_path / "production.db"
    sandbox_path = tmp_path / "sandbox.db"
    prod_conn = sqlite3.connect(prod_path)
    prod_conn.execute("CREATE TABLE IF NOT EXISTS production_guard (id TEXT PRIMARY KEY)")
    prod_conn.execute("INSERT INTO production_guard (id) VALUES (?)", ("sentinel",))
    prod_conn.commit()

    sandbox_conn = open_validation_sandbox(sandbox_path)
    rid = create_candidate(
        sandbox_conn,
        source="deterministic",
        description="test isolation",
        proposed_action="Suggestion only: no-op",
    )
    _ = run_validation(
        sandbox_conn,
        remediation_id=rid,
        before_state={"error_count": 2, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )

    guard = prod_conn.execute("SELECT COUNT(*) FROM production_guard").fetchone()
    assert int(guard[0]) == 1
    # Validation tables should not exist in production DB.
    prod_tables = {
        str(r[0])
        for r in prod_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "remediation_candidates" not in prod_tables
    assert "validation_runs" not in prod_tables
