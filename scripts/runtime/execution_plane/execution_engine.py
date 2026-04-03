"""Mock execution: approved + kill-switch checks only."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME = Path(__file__).resolve().parent.parent
for _p in (_RUNTIME, _ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

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
    jack_meta: dict = {}
    try:
        from modules.anna_training.jack_executor_bridge import maybe_delegate_to_jack

        jack_meta = maybe_delegate_to_jack(
            execution_request=req,
            mock_execution_result=result,
        )
    except Exception as e:  # noqa: BLE001 — never fail execution plane on delegate
        jack_meta = {"delegated": False, "reason": f"jack_bridge_import_or_run:{e!s}"}
    out = {**result, "outcome": outcome, "insight": insight}
    if jack_meta:
        out["jack_delegate"] = jack_meta
    return out
