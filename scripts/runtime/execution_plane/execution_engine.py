"""Mock execution: approved + kill-switch checks only."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learning_loop.outcome_tracker import record_execution_feedback

from .approval_manager import get_request
from .audit_logger import log_audit
from .kill_switch import is_active


def run_execution(request_id: str) -> dict[str, Any]:
    log_audit("execution_attempted", {"request_id": request_id})

    if is_active():
        result: dict[str, Any] = {
            "status": "blocked",
            "reason": "kill switch active",
            "request_id": request_id,
        }
        outcome, insight = record_execution_feedback(result)
        return {**result, "outcome": outcome, "insight": insight}

    req = get_request(request_id)
    if not req:
        result = {"status": "blocked", "reason": "unknown request", "request_id": request_id}
        outcome, insight = record_execution_feedback(result)
        return {**result, "outcome": outcome, "insight": insight}

    if req.get("approval_status") != "approved":
        result = {"status": "blocked", "reason": "not approved", "request_id": request_id}
        outcome, insight = record_execution_feedback(result)
        return {**result, "outcome": outcome, "insight": insight}

    result = {
        "status": "executed",
        "reason": "mock execution completed",
        "request_id": request_id,
    }
    outcome, insight = record_execution_feedback(result)
    return {**result, "outcome": outcome, "insight": insight}
