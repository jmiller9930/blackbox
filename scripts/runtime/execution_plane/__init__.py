"""
Execution plane (mock): approval-gated execution, audit, kill switch.

Phase 4.4 adds outcome + insight feedback via `learning_loop` (`execution_feedback_v1` rows).

No wallets, exchanges, or secrets. Uses existing SQLite `system_events` (no schema change).
"""
from __future__ import annotations

from .approval_manager import (
    approve_request,
    create_request,
    get_request,
    latest_request_id,
    reject_request,
)
from .execution_engine import run_execution
from .kill_switch import disable as kill_switch_disable
from .kill_switch import enable as kill_switch_enable
from .kill_switch import is_active as kill_switch_is_active
from .kill_switch import toggle as kill_switch_toggle

__all__ = [
    "approve_request",
    "create_request",
    "get_request",
    "latest_request_id",
    "reject_request",
    "run_execution",
    "kill_switch_disable",
    "kill_switch_enable",
    "kill_switch_is_active",
    "kill_switch_toggle",
]
