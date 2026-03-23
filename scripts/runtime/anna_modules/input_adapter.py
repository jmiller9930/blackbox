"""
Input adaptation: optional SQLite-backed artifacts, null-safe packaging.

Loads market snapshot, decision context, system trend, guardrail policy from `tasks`.
"""
from __future__ import annotations

import json
from typing import Any

from analyst_decision_engine import load_latest_stored_decision_context
from guardrail_policy_evaluator import load_latest_stored_system_trend


def load_latest_market_snapshot(conn) -> tuple[dict[str, Any] | None, str | None]:
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[Market Snapshot]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        return None, "No [Market Snapshot] task found in database."
    try:
        data = json.loads(row[1])
    except json.JSONDecodeError:
        return None, "Latest [Market Snapshot] row is not valid JSON."
    if data.get("kind") != "market_snapshot_v1":
        return None, "Latest market task is not market_snapshot_v1."
    return data, None


def load_latest_guardrail_policy(conn) -> tuple[dict[str, Any] | None, str | None]:
    row = conn.execute(
        """
        SELECT description FROM tasks
        WHERE title LIKE '[Guardrail Policy]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[0]:
        return None, "No [Guardrail Policy] task found."
    try:
        data = json.loads(row[0])
    except json.JSONDecodeError:
        return None, "Latest [Guardrail Policy] row is not valid JSON."
    if data.get("kind") != "guardrail_policy_v1":
        return None, "Latest policy task is not guardrail_policy_v1."
    return data, None


def try_load_decision_context(conn) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return load_latest_stored_decision_context(conn), None
    except (LookupError, ValueError, json.JSONDecodeError):
        return None, "No valid [Decision Context] with decision_context_v1."


def try_load_trend(conn) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return load_latest_stored_system_trend(conn), None
    except (LookupError, ValueError, json.JSONDecodeError):
        return None, "No valid [System Trend] with system_trend_v1."


def readiness_from_context(ctx: dict | None) -> str | None:
    if not ctx:
        return None
    r = ctx.get("system_readiness")
    if r in ("healthy", "degraded", "unstable"):
        return r
    return None


def guardrail_mode_from_policy(policy: dict[str, Any] | None) -> str:
    if not policy:
        return "unknown"
    raw = policy.get("mode")
    if raw in ("FROZEN", "CAUTION", "NORMAL"):
        return raw
    return "unknown"
