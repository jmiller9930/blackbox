"""Twig 4.5 — remediation pattern registry (sandbox, knowledge-only)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from learning_core.remediation_pattern_registry import (
    STATUS_CANDIDATE,
    STATUS_DEPRECATED,
    STATUS_REJECTED,
    STATUS_VALIDATED,
    deprecate_validated_pattern,
    list_patterns,
    pattern_is_rejected_and_never_reusable,
    pattern_is_sandbox_validated_knowledge_not_execution_approval,
    promote_candidate_to_validated_pattern,
    register_pattern_from_outcome_analysis,
    reject_candidate_pattern,
)
from learning_core.remediation_validation import create_candidate, open_validation_sandbox, run_validation
from learning_core.validation_outcome_analysis import OUTCOME_VALIDATED_SUCCESS, analyze_and_persist


def _sandbox_with_passing_analysis(tmp_path: Path) -> tuple:
    db = tmp_path / "sb.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="d",
        proposed_action="a",
        evidence=["e1"],
    )
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 2, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )
    an = analyze_and_persist(conn, str(vr["run_id"]))
    return conn, an["analysis_id"], rid


def _sandbox_with_failing_analysis(tmp_path: Path) -> tuple:
    db = tmp_path / "sb.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="d",
        proposed_action="a",
        evidence=["e1"],
    )
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 5, "metric_score": 0.9},
        after_state={"error_count": 5, "metric_score": 0.8, "regression_detected": True, "stable_window": False},
    )
    an = analyze_and_persist(conn, str(vr["run_id"]))
    return conn, an["analysis_id"], rid


def test_register_success_becomes_candidate_then_promote(tmp_path: Path) -> None:
    conn, aid, _rid = _sandbox_with_passing_analysis(tmp_path)
    pid = register_pattern_from_outcome_analysis(conn, aid)
    p = conn.execute(
        "SELECT pattern_status, outcome_category FROM remediation_patterns WHERE pattern_id = ?",
        (pid,),
    ).fetchone()
    assert p is not None
    assert str(p[0]) == STATUS_CANDIDATE
    assert str(p[1]) == OUTCOME_VALIDATED_SUCCESS

    promoted = promote_candidate_to_validated_pattern(conn, pid)
    assert promoted.pattern_status == STATUS_VALIDATED
    assert pattern_is_sandbox_validated_knowledge_not_execution_approval(promoted) is True

    dep = deprecate_validated_pattern(conn, pid)
    assert dep.pattern_status == STATUS_DEPRECATED


def test_register_failure_becomes_rejected_terminal(tmp_path: Path) -> None:
    conn, aid, _rid = _sandbox_with_failing_analysis(tmp_path)
    pid = register_pattern_from_outcome_analysis(conn, aid)
    p = conn.execute(
        "SELECT pattern_status FROM remediation_patterns WHERE pattern_id = ?",
        (pid,),
    ).fetchone()
    assert str(p[0]) == STATUS_REJECTED

    from learning_core.remediation_pattern_registry import get_pattern

    pat = get_pattern(conn, pid)
    assert pat is not None
    assert pattern_is_rejected_and_never_reusable(pat) is True

    with pytest.raises(ValueError):
        promote_candidate_to_validated_pattern(conn, pid)


def test_traceability_columns_populated(tmp_path: Path) -> None:
    conn, aid, rid = _sandbox_with_passing_analysis(tmp_path)
    pid = register_pattern_from_outcome_analysis(conn, aid)
    row = conn.execute(
        """
        SELECT source_remediation_id, validation_run_id, outcome_analysis_id
        FROM remediation_patterns WHERE pattern_id = ?
        """,
        (pid,),
    ).fetchone()
    assert row is not None
    assert str(row[0]) == rid
    run_id = conn.execute(
        "SELECT validation_run_id FROM validation_outcome_analyses WHERE analysis_id = ?",
        (aid,),
    ).fetchone()
    assert run_id is not None
    assert str(row[1]) == str(run_id[0])
    assert str(row[2]) == aid


def test_duplicate_register_raises(tmp_path: Path) -> None:
    conn, aid, _ = _sandbox_with_passing_analysis(tmp_path)
    register_pattern_from_outcome_analysis(conn, aid)
    with pytest.raises(Exception):  # sqlite IntegrityError
        register_pattern_from_outcome_analysis(conn, aid)


def test_reject_candidate_explicit(tmp_path: Path) -> None:
    conn, aid, _ = _sandbox_with_passing_analysis(tmp_path)
    pid = register_pattern_from_outcome_analysis(conn, aid)
    rj = reject_candidate_pattern(conn, pid, notes="abandon")
    assert rj.pattern_status == STATUS_REJECTED
    with pytest.raises(ValueError):
        promote_candidate_to_validated_pattern(conn, pid)


def test_deprecate_from_candidate_fails(tmp_path: Path) -> None:
    conn, aid, _ = _sandbox_with_passing_analysis(tmp_path)
    pid = register_pattern_from_outcome_analysis(conn, aid)
    with pytest.raises(ValueError):
        deprecate_validated_pattern(conn, pid)


def test_list_patterns_filter(tmp_path: Path) -> None:
    conn, aid_fail, _ = _sandbox_with_failing_analysis(tmp_path)
    register_pattern_from_outcome_analysis(conn, aid_fail)
    rej = list_patterns(conn, pattern_status=STATUS_REJECTED, limit=10)
    assert len(rej) == 1


def test_sandbox_only_no_production(tmp_path: Path) -> None:
    """Registry uses same open_validation_sandbox as other tests — isolation by construction."""
    conn, aid, _ = _sandbox_with_passing_analysis(tmp_path)
    pid = register_pattern_from_outcome_analysis(conn, aid)
    assert pid


def test_evidence_required_non_empty(tmp_path: Path) -> None:
    db = tmp_path / "x.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(conn, source="d", description="d", proposed_action="a", evidence=["e"])
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 1, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )
    an = analyze_and_persist(conn, str(vr["run_id"]))
    aid = str(an["analysis_id"])
    conn.execute(
        "UPDATE validation_outcome_analyses SET evidence_summary_json = ? WHERE analysis_id = ?",
        ("{}", aid),
    )
    conn.commit()
    with pytest.raises(ValueError, match="non-empty"):
        register_pattern_from_outcome_analysis(conn, aid)


def test_history_rows_on_promote_and_deprecate(tmp_path: Path) -> None:
    conn, aid, _ = _sandbox_with_passing_analysis(tmp_path)
    pid = register_pattern_from_outcome_analysis(conn, aid)
    promote_candidate_to_validated_pattern(conn, pid)
    deprecate_validated_pattern(conn, pid)
    n = conn.execute("SELECT COUNT(*) FROM remediation_pattern_history WHERE pattern_id = ?", (pid,)).fetchone()
    assert int(n[0]) >= 2
