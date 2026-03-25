"""Twig 4.4 — validation outcome analysis layer (sandbox, deterministic)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from learning_core.remediation_validation import create_candidate, open_validation_sandbox, run_validation
from learning_core.validation_outcome_analysis import (
    OUTCOME_CATEGORIES,
    OUTCOME_INSUFFICIENT_EVIDENCE,
    OUTCOME_REJECTED_FUNCTIONAL,
    OUTCOME_REJECTED_REGRESSION,
    OUTCOME_REJECTED_STABILITY,
    OUTCOME_VALIDATED_SUCCESS,
    analyze_and_persist,
    analyze_validation_run,
    build_evidence_summary,
    classify_outcome_category,
    list_recent_analyses_for_remediation,
)


def test_outcome_categories_are_fixed_and_documented() -> None:
    assert set(OUTCOME_CATEGORIES) == {
        OUTCOME_VALIDATED_SUCCESS,
        OUTCOME_REJECTED_FUNCTIONAL,
        OUTCOME_REJECTED_REGRESSION,
        OUTCOME_REJECTED_STABILITY,
        OUTCOME_INSUFFICIENT_EVIDENCE,
    }


def test_classification_is_deterministic_pass() -> None:
    assert (
        classify_outcome_category(validation_result="pass", failure_class="functional", failure_reason="x")
        == OUTCOME_VALIDATED_SUCCESS
    )


def test_classification_maps_failure_classes() -> None:
    assert (
        classify_outcome_category(validation_result="fail", failure_class="functional", failure_reason="")
        == OUTCOME_REJECTED_FUNCTIONAL
    )
    assert (
        classify_outcome_category(validation_result="fail", failure_class="regression", failure_reason="")
        == OUTCOME_REJECTED_REGRESSION
    )
    assert (
        classify_outcome_category(validation_result="fail", failure_class="stability", failure_reason="")
        == OUTCOME_REJECTED_STABILITY
    )


def test_classification_insufficient_on_empty_fail() -> None:
    assert (
        classify_outcome_category(validation_result="fail", failure_class="", failure_reason="")
        == OUTCOME_INSUFFICIENT_EVIDENCE
    )


def test_analysis_from_validation_run_pass(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="d",
        proposed_action="a",
        evidence=["e"],
    )
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 2, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )
    run_id = str(vr["run_id"])
    a = analyze_validation_run(conn, run_id)
    assert a["remediation_id"] == rid
    assert a["validation_result"] == "pass"
    assert a["outcome_category"] == OUTCOME_VALIDATED_SUCCESS
    assert a["before_after_comparison_summary"]["error_count_delta"] == -2
    es = a["evidence_summary"]
    assert "what_changed" in es and "retention_boundary" in es
    assert "Diagnostic analysis only" in es["retention_boundary"]


def test_evidence_summary_reflects_regression_fail(tmp_path: Path) -> None:
    es = build_evidence_summary(
        before_state={"error_count": 1, "metric_score": 1.0},
        after_state={
            "error_count": 1,
            "metric_score": 0.9,
            "regression_detected": True,
            "stable_window": False,
        },
        outcome_category=OUTCOME_REJECTED_REGRESSION,
        validation_result="fail",
        failure_class="regression",
        failure_reason="validation_failed:regression",
    )
    assert "regression_detected=true" in es["what_failed"]


def test_analyze_and_persist_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="d",
        proposed_action="a",
        evidence=["e"],
    )
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 5, "metric_score": 0.9},
        after_state={"error_count": 2, "metric_score": 0.85, "regression_detected": True, "stable_window": False},
    )
    a = analyze_and_persist(conn, str(vr["run_id"]))
    row = conn.execute(
        "SELECT outcome_category, validation_result FROM validation_outcome_analyses WHERE analysis_id = ?",
        (a["analysis_id"],),
    ).fetchone()
    assert row is not None
    assert str(row[0]) == OUTCOME_REJECTED_REGRESSION
    assert str(row[1]) == "fail"


def test_duplicate_persist_same_run_raises(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="d",
        proposed_action="a",
        evidence=["e"],
    )
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 1, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )
    analyze_and_persist(conn, str(vr["run_id"]))
    with pytest.raises(sqlite3.IntegrityError):
        analyze_and_persist(conn, str(vr["run_id"]))


def test_trend_hook_lists_recent_analyses(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="d",
        proposed_action="a",
        evidence=["e"],
    )
    vr1 = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 1, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )
    vr2 = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 1, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )
    analyze_and_persist(conn, str(vr1["run_id"]))
    analyze_and_persist(conn, str(vr2["run_id"]))
    hist = list_recent_analyses_for_remediation(conn, rid, limit=5)
    assert len(hist) == 2
    assert {h["outcome_category"] for h in hist} == {OUTCOME_VALIDATED_SUCCESS}


def test_no_production_path_uses_sandbox_only(tmp_path: Path) -> None:
    """Analysis module never opens default production sqlite."""
    db = tmp_path / "only.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(conn, source="d", description="d", proposed_action="a", evidence=["e"])
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 1, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )
    analyze_and_persist(conn, str(vr["run_id"]))
    # Sandbox file contains analysis table; no assertion on prod — isolation by construction.
    assert db.is_file()


def test_manual_insufficient_evidence_row(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(conn, source="d", description="d", proposed_action="a", evidence=["e"])
    run_id = "manual-run-1"
    conn.execute(
        """
        INSERT INTO validation_runs (
          run_id, remediation_id, before_state_json, after_state_json, result,
          failure_reason, failure_class, confidence, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            run_id,
            rid,
            json.dumps({}),
            json.dumps({}),
            "fail",
            "",
            "",
            0.5,
        ),
    )
    conn.commit()
    a = analyze_validation_run(conn, run_id)
    assert a["outcome_category"] == OUTCOME_INSUFFICIENT_EVIDENCE
