"""Append-only execution feedback rows in system_events (one row per attempt)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anna_modules.util import utc_now
from execution_plane.audit_logger import log_audit

from .insight_engine import build_insight


def build_outcome_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": result["request_id"],
        "status": result["status"],
        "reason": result["reason"],
        "timestamp": utc_now(),
    }


def record_execution_feedback(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Persist one system_events row (event_type=execution_feedback_v1) with outcome + insight.
    Append-only: never updates prior rows.
    """
    outcome = build_outcome_record(result)
    insight = build_insight(outcome)
    payload = {
        "kind": "execution_feedback_v1",
        "schema_version": 1,
        "outcome": outcome,
        "insight": insight,
    }
    log_audit("execution_feedback_v1", payload)
    return outcome, insight
