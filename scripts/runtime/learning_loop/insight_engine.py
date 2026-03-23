"""Deterministic insights from execution outcomes (no ML). Logic keys off structured fields, not free-text parsing."""
from __future__ import annotations

from typing import Any, Literal

InsightKind = Literal[
    "execution_succeeded",
    "blocked_not_approved",
    "blocked_kill_switch",
    "blocked_unknown_request",
]


def _classify(outcome: dict[str, Any]) -> tuple[InsightKind, str, Literal["success", "failure"]]:
    status = outcome.get("status")
    reason = str(outcome.get("reason") or "")
    rid = str(outcome.get("request_id") or "")

    if status == "executed":
        return (
            "execution_succeeded",
            (
                "Mock execution completed: request was approved, kill switch was inactive, "
                "and the execution plane allowed the run."
            ),
            "success",
        )
    if status == "blocked":
        if reason == "kill switch active":
            return (
                "blocked_kill_switch",
                "Execution was blocked because the kill switch is active; no execution is permitted until it is cleared.",
                "failure",
            )
        if reason == "unknown request":
            return (
                "blocked_unknown_request",
                "Execution was blocked because no execution_request_v1 exists for this request_id.",
                "failure",
            )
        if reason == "not approved":
            return (
                "blocked_not_approved",
                "Execution was blocked because the request is not approved; policy requires approval before execution.",
                "failure",
            )
        return (
            "blocked_unknown_request",
            f"Execution was blocked with unrecognized reason: {reason!r}.",
            "failure",
        )
    return (
        "blocked_unknown_request",
        f"Unexpected status {status!r} for request {rid!r}.",
        "failure",
    )


def build_insight(outcome: dict[str, Any]) -> dict[str, Any]:
    """
    Input: outcome record with request_id, status, reason, timestamp.

    Output: fixed contract for downstream consumers (insight_kind is the stable key).
    """
    kind, reasoning, typ = _classify(outcome)
    rid = str(outcome.get("request_id") or "")
    return {
        "insight_kind": kind,
        "type": typ,
        "reasoning": reasoning,
        "linked_request_id": rid,
    }
