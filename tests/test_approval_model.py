"""Twig 6 approval model — sandbox only, no execution."""

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
    STATUS_DEFERRED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_REJECTED,
    approve_pending,
    create_approval_request,
    defer_pending,
    get_approval,
    reject_pending,
    resolve_eligibility,
)
from learning_core.remediation_validation import assert_non_production_sqlite_path, open_validation_sandbox
from playground.run_data_pipeline import run_data_pipeline


def _seed_sandbox_with_pipeline(tmp_path: Path) -> tuple[Path, str]:
    sb = tmp_path / "ap.db"
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


def test_create_approve_lifecycle(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="test_operator")
        assert row["status"] == STATUS_PENDING
        aid = row["approval_id"]

        ap = approve_pending(conn, approval_id=aid, approved_by="architect", ttl_hours=24)
        assert ap["status"] == STATUS_APPROVED
        assert ap["approved_by"] == "architect"
        assert ap["expiration_timestamp"] is not None
    finally:
        conn.close()


def test_reject_pending(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        rj = reject_pending(conn, approval_id=aid, approved_by="architect")
        assert rj["status"] == STATUS_REJECTED
    finally:
        conn.close()


def test_defer_pending(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        d = defer_pending(conn, approval_id=aid, approved_by="architect", decision_note="later")
        assert d["status"] == STATUS_DEFERRED
        assert d.get("decision_note") == "later"
    finally:
        conn.close()


def test_invalid_double_approve(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="a", ttl_hours=1)
        with pytest.raises(ValueError, match="PENDING"):
            approve_pending(conn, approval_id=aid, approved_by="b", ttl_hours=1)
    finally:
        conn.close()


def test_eligibility_fails_without_pass_validation(tmp_path: Path) -> None:
    sb = tmp_path / "empty.db"
    conn = open_validation_sandbox(sb)
    try:
        with pytest.raises(ValueError, match="not found"):
            resolve_eligibility(conn, "missing-id")
    finally:
        conn.close()


def test_expired_marked_on_read(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="t")
        aid = row["approval_id"]
        approve_pending(conn, approval_id=aid, approved_by="a", ttl_hours=0)
        conn.execute(
            "UPDATE approvals SET expiration_timestamp = ? WHERE approval_id = ?",
            ("2000-01-01T00:00:00Z", aid),
        )
        conn.commit()
        ap = get_approval(conn, aid)
        assert ap is not None
        assert ap["status"] == STATUS_EXPIRED
    finally:
        conn.close()


def test_approval_cli_imports() -> None:
    path = RUNTIME / "approval_cli.py"
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


def test_approval_model_imports() -> None:
    path = RUNTIME / "learning_core" / "approval_model.py"
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


def test_cli_subprocess_create_and_status(tmp_path: Path) -> None:
    sb, rid = _seed_sandbox_with_pipeline(tmp_path)
    cli = RUNTIME / "approval_cli.py"
    p = subprocess.run(
        [
            sys.executable,
            str(cli),
            "--sandbox-db",
            str(sb),
            "--create",
            "--source-remediation-id",
            rid,
            "--requested-by",
            "pytest",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, p.stderr + p.stdout
    data = json.loads(p.stdout.strip())
    assert data["ok"] is True
    assert data["approval"]["source_remediation_id"] == rid
    aid = data["approval"]["approval_id"]

    p2 = subprocess.run(
        [
            sys.executable,
            str(cli),
            "--sandbox-db",
            str(sb),
            "--status",
            "--approval-id",
            aid,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p2.returncode == 0
    st = json.loads(p2.stdout.strip())
    assert st["ok"] is True
    assert st["approval"]["status"] == STATUS_PENDING


def test_sandbox_rejects_production_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"
    monkeypatch.setenv("BLACKBOX_SQLITE_PATH", str(prod))
    with pytest.raises(ValueError):
        assert_non_production_sqlite_path(prod)


def test_approvals_table_exists(tmp_path: Path) -> None:
    sb = tmp_path / "t.db"
    conn = open_validation_sandbox(sb)
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='approvals'"
        ).fetchone()
        assert row is not None
        assert "approval_id" in row[0]
        assert "source_remediation_id" in row[0]
    finally:
        conn.close()
