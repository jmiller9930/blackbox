"""Twig 5 — remediation execution simulator (sandbox, simulation-only)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from learning_core.remediation_execution_simulator import (
    evaluate_simulation_policy,
    simulate_and_record_remediation_execution,
)
from learning_core.remediation_pattern_registry import (
    promote_candidate_to_validated_pattern,
    register_pattern_from_outcome_analysis,
)
from learning_core.remediation_validation import create_candidate, open_validation_sandbox, run_validation
from learning_core.validation_outcome_analysis import analyze_and_persist


def _validated_pattern_and_ids(tmp_path: Path) -> tuple:
    db = tmp_path / "sb.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(
        conn,
        source="deterministic",
        description="reduce errors",
        proposed_action="Suggestion only: tune retries",
        evidence=["ev1"],
    )
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 2, "metric_score": 1.0},
        after_state={"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True},
    )
    an = analyze_and_persist(conn, str(vr["run_id"]))
    pid = register_pattern_from_outcome_analysis(conn, str(an["analysis_id"]))
    promote_candidate_to_validated_pattern(conn, pid)
    return conn, pid, rid


def test_policy_always_blocks_real_execution() -> None:
    p = evaluate_simulation_policy({"hypothetical_approval_granted": True, "maintenance_window_active": True})
    assert p["would_allow_real_execution"] is False
    assert p["approval_required"] is True
    assert "simulation_phase_no_real_execution_hook" in p["execution_blocked_reason"]


def test_simulation_success_path_deterministic_logic(tmp_path: Path) -> None:
    conn, pat_id, rid = _validated_pattern_and_ids(tmp_path)
    ctx = {
        "synthetic_apply_succeeds": True,
        "synthetic_rollback_failure": False,
        "maintenance_window_active": False,
    }
    a = simulate_and_record_remediation_execution(conn, pattern_id=pat_id, remediation_id=rid, validation_context=ctx)
    b = simulate_and_record_remediation_execution(conn, pattern_id=pat_id, remediation_id=rid, validation_context=ctx)
    for x in (a, b):
        assert x["result"] == "success"
        assert x["failure_class"] == ""
        assert x["rollback_attempted"] is True
        assert x["rollback_success"] is True
        assert x["policy"]["would_allow_real_execution"] is False
    assert a["failure_reason"] == b["failure_reason"]


def test_rollback_failure_class_regression(tmp_path: Path) -> None:
    conn, pat_id, rid = _validated_pattern_and_ids(tmp_path)
    out = simulate_and_record_remediation_execution(
        conn,
        pattern_id=pat_id,
        remediation_id=rid,
        validation_context={"synthetic_apply_succeeds": True, "synthetic_rollback_failure": True},
    )
    assert out["result"] == "fail"
    assert out["failure_class"] == "regression"
    assert out["rollback_attempted"] is True
    assert out["rollback_success"] is False


def test_apply_fail_no_rollback(tmp_path: Path) -> None:
    conn, pat_id, rid = _validated_pattern_and_ids(tmp_path)
    out = simulate_and_record_remediation_execution(
        conn,
        pattern_id=pat_id,
        remediation_id=rid,
        validation_context={"synthetic_apply_succeeds": False},
    )
    assert out["rollback_attempted"] is False
    assert out["rollback_success"] is False
    assert out["failure_class"] == "functional"


def test_rejected_pattern_fails_fast(tmp_path: Path) -> None:
    db = tmp_path / "r.db"
    conn = open_validation_sandbox(db)
    rid = create_candidate(conn, source="d", description="d", proposed_action="a", evidence=["e"])
    vr = run_validation(
        conn,
        remediation_id=rid,
        before_state={"error_count": 3, "metric_score": 1.0},
        after_state={"error_count": 3, "metric_score": 0.9, "regression_detected": True, "stable_window": False},
    )
    an = analyze_and_persist(conn, str(vr["run_id"]))
    pid = register_pattern_from_outcome_analysis(conn, str(an["analysis_id"]))
    out = simulate_and_record_remediation_execution(conn, pattern_id=pid, remediation_id=rid, validation_context={})
    assert out["failure_class"] == "functional"
    assert out["rollback_attempted"] is False


def test_remediation_mismatch_raises(tmp_path: Path) -> None:
    conn, pat_id, rid = _validated_pattern_and_ids(tmp_path)
    with pytest.raises(ValueError):
        simulate_and_record_remediation_execution(conn, pattern_id=pat_id, remediation_id="wrong-id", validation_context={})


def test_sandbox_table_persisted(tmp_path: Path) -> None:
    conn, pat_id, rid = _validated_pattern_and_ids(tmp_path)
    out = simulate_and_record_remediation_execution(conn, pattern_id=pat_id, remediation_id=rid, validation_context={})
    n = conn.execute(
        "SELECT COUNT(*) FROM remediation_execution_simulations WHERE execution_simulation_id = ?",
        (out["execution_simulation_id"],),
    ).fetchone()
    assert int(n[0]) == 1


def test_simulator_module_has_no_data_or_telegram_imports() -> None:
    path = ROOT / "scripts" / "runtime" / "learning_core" / "remediation_execution_simulator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[0])
        if isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    assert "telegram_interface" not in names
    assert "data_status" not in names


def test_production_sqlite_path_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from learning_core.remediation_validation import open_validation_sandbox
    from _paths import default_sqlite_path

    prod = tmp_path / "prod.db"
    monkeypatch.setenv("BLACKBOX_SQLITE_PATH", str(prod))
    with pytest.raises(ValueError):
        open_validation_sandbox(default_sqlite_path())
