"""4.6.3.2 Part B Step 2 — execution-aware diagnostics (no remediation)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from _db import ensure_schema
from _paths import repo_root
from execution_plane.approval_manager import create_request
from learning_core.data_execution_aware import (
    classify_infra_action,
    evaluate_action_safety,
    get_execution_state_snapshot,
    is_maintenance_window_open,
)
from telegram_interface.agent_dispatcher import dispatch
from telegram_interface.message_router import RoutedMessage


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn, repo_root())
    return conn


def test_execution_sensitive_state_detected_with_pending_request() -> None:
    create_request()
    snap = get_execution_state_snapshot()
    assert snap["pending_execution_requests"] >= 1
    assert snap["execution_sensitive"] is True


def test_action_classification_categories() -> None:
    assert classify_infra_action("read_health") == "safe"
    assert classify_infra_action("restart_service") == "controlled"
    assert classify_infra_action("power_off") == "blocked"


def test_controlled_action_deferred_when_sensitive() -> None:
    out = evaluate_action_safety(
        action_name="restart_service",
        state_snapshot={"execution_sensitive": True},
    )
    assert out["classification"] == "controlled"
    assert out["defer"] is True
    assert "execution-sensitive" in out["reason"]


def test_blocked_action_is_blocked() -> None:
    out = evaluate_action_safety(
        action_name="power_off",
        state_snapshot={"execution_sensitive": False},
    )
    assert out["classification"] == "blocked"
    assert out["defer"] is True


def test_maintenance_window_placeholder_defaults_false() -> None:
    assert is_maintenance_window_open() is False


def test_data_output_behavior_unchanged_for_status_mode() -> None:
    payload = dispatch(RoutedMessage("data", "", data_mode="status"))
    assert payload["kind"] == "data"
    assert payload["data_mode"] == "status"
    assert "Current phase:" in str(payload.get("status_text") or "")
