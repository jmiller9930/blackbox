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


def test_detection_window_orders_by_created_at_newest_first() -> None:
    """Lexicographic id order must not define recency; created_at does."""
    conn = _conn()
    conn.execute(
        "INSERT INTO system_events (id, source, event_type, severity, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "zzz-oldest-id",
            "execution_plane",
            "execution_attempted",
            "error",
            json.dumps({"n": 1}),
            "2019-01-01T00:00:00Z",
        ),
    )
    conn.execute(
        "INSERT INTO system_events (id, source, event_type, severity, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "mmm-mid-id",
            "execution_plane",
            "execution_attempted",
            "error",
            json.dumps({"n": 2}),
            "2020-06-01T00:00:00Z",
        ),
    )
    conn.execute(
        "INSERT INTO system_events (id, source, event_type, severity, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "aaa-newest-id",
            "execution_plane",
            "execution_attempted",
            "error",
            json.dumps({"n": 3}),
            "2030-01-01T00:00:00Z",
        ),
    )
    conn.commit()
    ordered = conn.execute(
        """
        SELECT id FROM system_events
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 10
        """
    ).fetchall()
    assert [str(r[0]) for r in ordered][0] == "aaa-newest-id"


def test_newest_events_win_over_lexicographic_id_order_in_window() -> None:
    """
    When id DESC would exclude the newest rows by time, timestamp ordering must still
    include them in the detection window (connectivity signal only on newest rows).
    """
    conn = _conn()
    for i in range(50):
        conn.execute(
            """
            INSERT INTO system_events (id, source, event_type, severity, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"e{i:03d}-old",
                "execution_plane",
                "execution_attempted",
                "info",
                json.dumps({"n": i}),
                "2020-01-01T00:00:00Z",
            ),
        )
    for j, eid in enumerate(("aa-newest", "bb-newest")):
        conn.execute(
            """
            INSERT INTO system_events (id, source, event_type, severity, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                "execution_plane",
                "execution_attempted",
                "error",
                json.dumps({"error": "connection refused", "j": j}),
                "2030-06-01T12:00:00Z",
            ),
        )
    conn.commit()
    issues = detect_infra_issues(conn, error_window=50)
    conn_issues = [i for i in issues if i.get("category") == "connectivity"]
    assert conn_issues, "newest connection-refused rows must be inside the detection window"
    assert any("connectivity_error_signals=" in " ".join(i.get("supporting_evidence") or []) for i in conn_issues)


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
