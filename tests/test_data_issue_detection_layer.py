"""4.6.3.2 Part B Twig 3 — issue detection + suggestion (no execution)."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from _db import ensure_schema, seed_agents
from _paths import repo_root
from learning_core.data_issue_detection import (
    build_issue_suggestion,
    detect_infra_issues,
)
from telegram_interface.agent_dispatcher import dispatch
from telegram_interface.message_router import RoutedMessage


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn, repo_root())
    seed_agents(conn)
    return conn


def test_issue_detection_correctness_and_classification_shape() -> None:
    conn = _conn()
    # Seed repeated error events + connectivity signal.
    for i in range(3):
        payload = {"error": "connection refused", "n": i}
        conn.execute(
            "INSERT INTO system_events (id, source, event_type, severity, payload) VALUES (?, ?, ?, ?, ?)",
            (f"e{i}", "execution_plane", "execution_attempted", "error", json.dumps(payload)),
        )
    conn.commit()
    now = datetime.now(timezone.utc)
    # stale market snapshot (8h old)
    old = (now - timedelta(hours=8)).isoformat().replace("+00:00", "Z")
    conn.execute(
        """
        INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("t1", "anna", "[Market Snapshot] old", "{}", "completed", "normal", old, old),
    )
    conn.commit()

    issues = detect_infra_issues(conn, now=now)
    assert len(issues) >= 2
    one = issues[0]
    for key in ("issue_id", "category", "severity", "confidence", "timestamp", "supporting_evidence"):
        assert key in one


def test_suggestion_generation_and_execution_aware_defer() -> None:
    conn = _conn()
    issue = {
        "issue_id": "x",
        "category": "database",
        "severity": "high",
        "confidence": 0.9,
        "timestamp": "2026-01-01T00:00:00Z",
        "supporting_evidence": ["db_lock_signals=2"],
    }
    execution_state = {"execution_sensitive": True}
    s = build_issue_suggestion(issue, execution_state=execution_state)
    assert s["llm_generated"] is False
    assert "Suggestion only" in s["suggested_fix"]
    assert isinstance(s["possible_causes"], list) and s["possible_causes"]
    assert s["safety"]["defer"] is True
    assert "execution-sensitive" in s["safety"]["reason"]


def test_no_runtime_mutation_from_detection_and_suggestion() -> None:
    conn = _conn()
    before_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    before_events = conn.execute("SELECT COUNT(*) FROM system_events").fetchone()[0]
    issues = detect_infra_issues(conn)
    for issue in issues:
        _ = build_issue_suggestion(issue, execution_state={"execution_sensitive": False})
    after_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    after_events = conn.execute("SELECT COUNT(*) FROM system_events").fetchone()[0]
    assert before_tasks == after_tasks
    assert before_events == after_events


def test_data_responses_unchanged_and_independent_from_detection() -> None:
    conn = _conn()
    _ = detect_infra_issues(conn)
    payload = dispatch(RoutedMessage("data", "", data_mode="status"))
    assert payload["kind"] == "data"
    assert payload["data_mode"] == "status"
    assert "Current phase:" in str(payload.get("status_text") or "")


def test_database_lock_detection_from_seeded_payload_signal() -> None:
    conn = _conn()
    conn.execute(
        "INSERT INTO system_events (id, source, event_type, severity, payload) VALUES (?, ?, ?, ?, ?)",
        (
            "lock1",
            "execution_plane",
            "execution_attempted",
            "error",
            json.dumps({"error": "database is locked"}),
        ),
    )
    conn.commit()
    issues = detect_infra_issues(conn)
    db_issues = [i for i in issues if i.get("category") == "database"]
    assert db_issues, "expected explicit database lock issue"
    assert any("db_lock_signals=" in " ".join(i.get("supporting_evidence") or []) for i in db_issues)
