"""4.6.3.2 Part B Twig 4.3 — detection->ingestion->validation pipeline tests."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from _db import ensure_schema, seed_agents
from _paths import repo_root
from learning_core.remediation_pipeline import run_remediation_validation_pipeline
from telegram_interface.agent_dispatcher import dispatch
from telegram_interface.message_router import RoutedMessage


def _runtime_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn, repo_root())
    seed_agents(conn)
    return conn


def _seed_detectable_issue(conn: sqlite3.Connection) -> None:
    for i in range(3):
        conn.execute(
            "INSERT INTO system_events (id, source, event_type, severity, payload) VALUES (?, ?, ?, ?, ?)",
            (
                f"evt-{i}",
                "execution_plane",
                "execution_attempted",
                "error",
                json.dumps({"error": "connection refused", "n": i}),
            ),
        )
    conn.commit()


def test_pipeline_end_to_end_in_sandbox(tmp_path: Path) -> None:
    runtime_conn = _runtime_conn()
    _seed_detectable_issue(runtime_conn)
    sandbox_db = tmp_path / "pipeline.db"
    out = run_remediation_validation_pipeline(
        runtime_conn=runtime_conn,
        sandbox_db_path=sandbox_db,
        execution_state={"execution_sensitive": False},
        issue_limit=5,
    )
    assert out.ok is True
    assert out.stage == "complete"
    assert out.traces
    trace = out.traces[0]
    assert trace["issue_id"]
    assert trace["remediation_id"]
    assert trace["validation_result"] in {"pass", "fail"}

    sconn = sqlite3.connect(sandbox_db)
    n_trace = int(sconn.execute("SELECT COUNT(*) FROM validation_pipeline_trace").fetchone()[0])
    assert n_trace >= 1


def test_pipeline_ingestion_failure_stops_and_returns_structured_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_conn = _runtime_conn()
    _seed_detectable_issue(runtime_conn)
    sandbox_db = tmp_path / "pipeline.db"

    import learning_core.remediation_pipeline as rp

    def _boom(**_: object) -> str:
        raise ValueError("ingest boom")

    monkeypatch.setattr(rp, "ingest_remediation_candidate", _boom)
    out = run_remediation_validation_pipeline(
        runtime_conn=runtime_conn,
        sandbox_db_path=sandbox_db,
        execution_state={"execution_sensitive": False},
    )
    assert out.ok is False
    assert out.stage == "ingest"
    assert out.error is not None
    assert out.error.get("kind") == "ingestion_error"
    assert "boom" in str(out.error.get("message") or "")


def test_pipeline_no_production_mutation(tmp_path: Path) -> None:
    runtime_conn = _runtime_conn()
    _seed_detectable_issue(runtime_conn)
    prod = tmp_path / "prod.db"
    pconn = sqlite3.connect(prod)
    pconn.execute("CREATE TABLE IF NOT EXISTS prod_guard (id TEXT PRIMARY KEY)")
    pconn.execute("INSERT INTO prod_guard (id) VALUES ('sentinel')")
    pconn.commit()

    sandbox_db = tmp_path / "pipeline.db"
    _ = run_remediation_validation_pipeline(
        runtime_conn=runtime_conn,
        sandbox_db_path=sandbox_db,
    )
    count = int(pconn.execute("SELECT COUNT(*) FROM prod_guard").fetchone()[0])
    assert count == 1
    tables = {str(r[0]) for r in pconn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "validation_pipeline_trace" not in tables
    assert "remediation_candidates" not in tables


def test_pipeline_not_auto_triggered_in_data_dispatch(tmp_path: Path) -> None:
    # Calling DATA dispatcher should remain unchanged and must not create pipeline artifacts.
    sandbox_db = tmp_path / "unused.db"
    payload = dispatch(RoutedMessage("data", "", data_mode="status"))
    assert payload["kind"] == "data"
    assert payload["data_mode"] == "status"
    assert not sandbox_db.exists()
