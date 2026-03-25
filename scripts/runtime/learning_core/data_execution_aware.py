"""4.6.3.2 Part B Step 2 — execution-aware DATA diagnostics (no remediation)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

ActionClass = Literal["safe", "controlled", "blocked"]

_SAFE_ACTIONS = {
    "read_health",
    "read_metrics",
    "inspect_learning_records",
    "inspect_transitions",
}
_CONTROLLED_ACTIONS = {
    "restart_service",
    "reload_config",
    "rotate_logs",
}
_BLOCKED_ACTIONS = {
    "power_off",
    "kill_execution_pipeline",
    "force_reset_runtime",
}


def classify_infra_action(action_name: str) -> ActionClass:
    a = (action_name or "").strip().lower()
    if a in _SAFE_ACTIONS:
        return "safe"
    if a in _CONTROLLED_ACTIONS:
        return "controlled"
    if a in _BLOCKED_ACTIONS:
        return "blocked"
    return "controlled"


def _load_requests(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_execution_state_snapshot(
    *,
    conn: sqlite3.Connection | None = None,
    requests_path: Path | None = None,
) -> dict[str, Any]:
    """
    Read-only execution-sensitive state snapshot.
    No mutation, no remediation, no execution-plane behavior changes.
    """
    from execution_plane.approval_manager import REQUESTS_PATH
    from execution_plane.kill_switch import is_active

    req_path = requests_path or REQUESTS_PATH
    reqs = _load_requests(req_path)
    pending = sum(1 for r in reqs.values() if str((r or {}).get("approval_status") or "") == "pending")
    approved = sum(1 for r in reqs.values() if str((r or {}).get("approval_status") or "") == "approved")
    in_progress = False
    if conn is not None:
        try:
            row = conn.execute(
                """
                SELECT event_type FROM system_events
                WHERE source = 'execution_plane'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if row and str(row[0]) == "execution_attempted":
                in_progress = True
        except Exception:
            in_progress = False
    sensitive = bool(pending > 0 or approved > 0 or in_progress)
    return {
        "kill_switch_active": bool(is_active()),
        "pending_execution_requests": int(pending),
        "approved_execution_requests": int(approved),
        "execution_pipeline_in_progress": bool(in_progress),
        "execution_sensitive": sensitive,
    }


def is_maintenance_window_open(*, now_iso: str | None = None) -> bool:
    """
    Placeholder hook for future maintenance-window policy.
    This step intentionally returns False (no autonomous maintenance gating yet).
    """
    _ = now_iso
    return False


def evaluate_action_safety(
    *,
    action_name: str,
    state_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """
    Diagnostics-only decision artifact: classify and optionally defer/report.
    Never executes remediation.
    """
    cls = classify_infra_action(action_name)
    sensitive = bool(state_snapshot.get("execution_sensitive"))
    if cls == "safe":
        return {
            "action": action_name,
            "classification": cls,
            "defer": False,
            "reason": "safe diagnostic action",
            "report_only": True,
        }
    if cls == "blocked":
        return {
            "action": action_name,
            "classification": cls,
            "defer": True,
            "reason": "blocked action in this phase",
            "report_only": True,
        }
    # controlled
    if sensitive:
        return {
            "action": action_name,
            "classification": cls,
            "defer": True,
            "reason": "execution-sensitive state active",
            "report_only": True,
        }
    return {
        "action": action_name,
        "classification": cls,
        "defer": True,
        "reason": "controlled action requires future maintenance-window + approval framework",
        "report_only": True,
    }
