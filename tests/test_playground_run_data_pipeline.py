"""Operator playground (Layer 1) — sandbox pipeline orchestration tests."""

from __future__ import annotations

import ast
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from playground.run_data_pipeline import _assert_not_production_sqlite, run_data_pipeline


def test_full_pipeline_seed_demo(tmp_path: Path) -> None:
    sb = tmp_path / "sandbox.db"
    r = run_data_pipeline(
        sandbox_db=sb,
        issue_db=None,
        replay_remediation_id=None,
        seed_demo=True,
        step_mode=False,
        quiet=True,
    )
    assert r["ok"] is True
    assert len(r["stages"]) == 7
    names = [s["name"] for s in r["stages"]]
    assert names == ["DETECT", "SUGGEST", "INGEST", "VALIDATE", "ANALYZE", "PATTERN", "SIMULATE"]
    conn = sqlite3.connect(sb)
    n = conn.execute("SELECT COUNT(*) FROM remediation_execution_simulations").fetchone()
    assert int(n[0]) >= 1
    conn.close()


def test_rejects_production_sandbox_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"
    monkeypatch.setenv("BLACKBOX_SQLITE_PATH", str(prod))
    with pytest.raises(SystemExit):
        _assert_not_production_sqlite(prod)


def test_step_mode_pauses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sb = tmp_path / "s.db"
    steps: list[str] = []

    def fake_input(_: str = "") -> str:
        steps.append("enter")
        return ""

    monkeypatch.setattr("builtins.input", fake_input)
    # step pauses only when not quiet (quiet skips prompts)
    run_data_pipeline(
        sandbox_db=sb,
        issue_db=None,
        replay_remediation_id=None,
        seed_demo=True,
        step_mode=True,
        quiet=False,
    )
    assert len(steps) >= 6


def test_replay_mode_skips_detect(tmp_path: Path) -> None:
    sb = tmp_path / "sb.db"
    first = run_data_pipeline(
        sandbox_db=sb,
        issue_db=None,
        replay_remediation_id=None,
        seed_demo=True,
        step_mode=False,
        quiet=True,
    )
    assert first["ok"] is True
    rid = str(first["remediation_id"])
    second = run_data_pipeline(
        sandbox_db=sb,
        issue_db=None,
        replay_remediation_id=rid,
        seed_demo=False,
        step_mode=False,
        quiet=True,
    )
    assert second["ok"] is True
    assert second["stages"][0]["name"] == "DETECT"
    assert second["stages"][0]["status"] == "blocked"


def test_playground_forbidden_imports() -> None:
    path = ROOT / "scripts" / "runtime" / "playground" / "run_data_pipeline.py"
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


def test_no_production_mutation(tmp_path: Path) -> None:
    prod = tmp_path / "production_isolation.db"
    prod.touch()
    sb = tmp_path / "sandbox.db"
    conn = sqlite3.connect(prod)
    conn.execute("CREATE TABLE IF NOT EXISTS guard (k TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO guard (k) VALUES ('x')")
    conn.commit()
    run_data_pipeline(
        sandbox_db=sb,
        issue_db=None,
        replay_remediation_id=None,
        seed_demo=True,
        step_mode=False,
        quiet=True,
    )
    n = conn.execute("SELECT COUNT(*) FROM guard").fetchone()
    assert int(n[0]) == 1
    conn.close()
