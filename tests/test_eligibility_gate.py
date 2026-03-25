"""4.6.3.7 execution eligibility gate — sandbox only, no execution."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scripts" / "runtime"
sys.path.insert(0, str(RUNTIME))

from learning_core.approval_model import (
    STATUS_APPROVED,
    approve_pending,
    create_approval_request,
)
from learning_core.eligibility_gate import ELIGIBLE, EXPIRED, INELIGIBLE, evaluate_eligibility, get_eligibility_record
from learning_core.remediation_validation import assert_non_production_sqlite_path, open_validation_sandbox
from playground.run_data_pipeline import run_data_pipeline


def _seed_sandbox_with_pipeline(tmp_path: Path) -> tuple[Path, str]:
    sb = tmp_path / "elig.db"
    r = run_data_pipeline(
        sandbox_db=sb,
        issue_db=None,
        replay_remediation_id=None,
        seed_demo=True,
        step_mode=False,
        quiet=True,
    )
    assert r["ok"] is True
    rid = str(r["remediation_id"])
    return sb, rid


def test_eligible_case(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="architect", ttl_hours=24)

        out = evaluate_eligibility(conn, approval_id=aid, evaluated_by="pytest")
        assert out["ok"] is True
        assert out["persisted"] is True
        assert out["eligibility_status"] == ELIGIBLE
        assert out["ineligibility_reason"] is None
        assert out["approval_id"] == aid

        st = get_eligibility_record(conn, out["eligibility_id"])
        assert st is not None
        assert st["eligibility_status"] == ELIGIBLE
    finally:
        conn.close()


def test_ineligible_not_approved(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        assert row["status"] != STATUS_APPROVED

        out = evaluate_eligibility(conn, approval_id=aid)
        assert out["ok"] is True
        assert out["persisted"] is True
        assert out["eligibility_status"] == INELIGIBLE
        assert out["ineligibility_reason"] == "approval_not_approved"
    finally:
        conn.close()


def test_approval_not_found(tmp_path: Path) -> None:
    sb = tmp_path / "e.db"
    conn = open_validation_sandbox(sb)
    try:
        out = evaluate_eligibility(conn, approval_id="00000000-0000-0000-0000-000000000001")
        assert out["ok"] is True
        assert out["persisted"] is True
        assert out["eligibility_status"] == INELIGIBLE
        assert out["ineligibility_reason"] == "approval_not_found"
        eid = out["eligibility_id"]
        st = get_eligibility_record(conn, eid)
        assert st is not None
        assert st["eligibility_status"] == INELIGIBLE
        assert st["ineligibility_reason"] == "approval_not_found"
    finally:
        conn.close()


def test_validation_run_not_found_persisted(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="a", ttl_hours=24)
        bad_run = "00000000-0000-0000-0000-000000000099"
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "UPDATE approvals SET validation_run_id = ? WHERE approval_id = ?",
            (bad_run, aid),
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()

        out = evaluate_eligibility(conn, approval_id=aid)
        assert out["ok"] is True
        assert out["persisted"] is True
        assert out["eligibility_status"] == INELIGIBLE
        assert out["ineligibility_reason"] == "validation_run_not_found"
        st = get_eligibility_record(conn, out["eligibility_id"])
        assert st is not None
        assert st["ineligibility_reason"] == "validation_run_not_found"
    finally:
        conn.close()


def test_simulation_not_found_persisted(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="a", ttl_hours=24)
        bad_sim = "00000000-0000-0000-0000-000000000088"
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "UPDATE approvals SET simulation_id = ? WHERE approval_id = ?",
            (bad_sim, aid),
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()

        out = evaluate_eligibility(conn, approval_id=aid)
        assert out["ok"] is True
        assert out["persisted"] is True
        assert out["eligibility_status"] == INELIGIBLE
        assert out["ineligibility_reason"] == "simulation_not_found"
        st = get_eligibility_record(conn, out["eligibility_id"])
        assert st is not None
        assert st["ineligibility_reason"] == "simulation_not_found"
    finally:
        conn.close()


def test_validation_failure_marks_ineligible(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="a", ttl_hours=24)
        vrun = row["validation_run_id"]
        conn.execute("UPDATE validation_runs SET result = 'fail' WHERE run_id = ?", (vrun,))
        conn.commit()

        out = evaluate_eligibility(conn, approval_id=aid)
        assert out["ok"] is True
        assert out["eligibility_status"] == INELIGIBLE
        assert out["ineligibility_reason"] == "validation_not_pass"
    finally:
        conn.close()


def test_simulation_policy_must_block_real_execution(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="a", ttl_hours=24)
        sim_id = row["simulation_id"]
        conn.execute(
            "UPDATE remediation_execution_simulations SET policy_json = ? WHERE execution_simulation_id = ?",
            ('{"would_allow_real_execution": true}', sim_id),
        )
        conn.commit()

        out = evaluate_eligibility(conn, approval_id=aid)
        assert out["ok"] is True
        assert out["eligibility_status"] == INELIGIBLE
        assert out["ineligibility_reason"] == "simulation_policy_must_have_would_allow_real_execution_false"
    finally:
        conn.close()


def test_expired_by_time_on_status(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="a", ttl_hours=24)
        out = evaluate_eligibility(conn, approval_id=aid)
        eid = out["eligibility_id"]
        conn.execute(
            "UPDATE eligibility SET expires_at = ? WHERE eligibility_id = ?",
            ("2000-01-01T00:00:00Z", eid),
        )
        conn.commit()

        st = get_eligibility_record(conn, eid)
        assert st is not None
        assert st["eligibility_status"] == EXPIRED
        assert st.get("expired_by_time") is True
    finally:
        conn.close()


def test_eligibility_cli_imports() -> None:
    path = RUNTIME / "eligibility_cli.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    banned = {"telegram_interface", "messaging_interface", "execution_plane", "data_status"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name.split(".")[0])
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    assert banned.isdisjoint(found)


def test_eligibility_gate_module_imports() -> None:
    path = RUNTIME / "learning_core" / "eligibility_gate.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    banned = {"telegram_interface", "messaging_interface", "execution_plane", "data_status"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name.split(".")[0])
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module.split(".")[0]
            if mod not in ("learning_core", "typing"):
                found.add(mod)
    assert banned.isdisjoint(found)


def test_cli_subprocess_evaluate_and_status(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    cli = RUNTIME / "eligibility_cli.py"
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="a", ttl_hours=24)
    finally:
        conn.close()

    p = subprocess.run(
        [
            sys.executable,
            str(cli),
            "--sandbox-db",
            str(sb),
            "--evaluate",
            "--approval-id",
            aid,
            "--evaluated-by",
            "cli_test",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, p.stderr + p.stdout
    data = json.loads(p.stdout.strip())
    assert data["ok"] is True
    assert data["eligibility_status"] == ELIGIBLE
    eid = data["eligibility_id"]

    p2 = subprocess.run(
        [
            sys.executable,
            str(cli),
            "--sandbox-db",
            str(sb),
            "--status",
            "--eligibility-id",
            eid,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p2.returncode == 0
    st = json.loads(p2.stdout.strip())
    assert st["ok"] is True
    assert st["eligibility"]["eligibility_id"] == eid


def test_sandbox_rejects_production_path_eligibility(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"
    monkeypatch.setenv("BLACKBOX_SQLITE_PATH", str(prod))
    with pytest.raises(ValueError):
        assert_non_production_sqlite_path(prod)


def test_eligibility_table_schema(tmp_path: Path) -> None:
    sb = tmp_path / "schema.db"
    conn = open_validation_sandbox(sb)
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='eligibility'"
        ).fetchone()
        assert row is not None
        sql = row[0]
        for needle in (
            "eligibility_id",
            "approval_id",
            "source_remediation_id",
            "validation_run_id",
            "simulation_id",
            "eligibility_status",
            "evaluated_at",
            "expires_at",
            "evaluated_by",
            "confidence_score",
            "risk_level",
            "ineligibility_reason",
        ):
            assert needle in sql
        assert "FOREIGN KEY" not in (sql or "").upper()
    finally:
        conn.close()
