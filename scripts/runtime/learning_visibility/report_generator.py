"""Human-readable reports from summary dicts only (no direct DB access)."""
from __future__ import annotations

from typing import Any


def _label_failure_kind(kind: str) -> str:
    return {
        "blocked_not_approved": "approval not granted",
        "blocked_kill_switch": "kill switch activation",
        "blocked_unknown_request": "unknown or missing request",
        "execution_succeeded": "success",
    }.get(kind, kind.replace("_", " "))


def generate_report(summary: dict[str, Any]) -> str:
    """
    Produce a short narrative from `summarize_insights` output only.
    """
    total = int(summary.get("total") or 0)
    success = int(summary.get("success") or 0)
    failure = int(summary.get("failure") or 0)
    by_type = summary.get("by_type") or {}

    if total == 0:
        return "No execution feedback matched the current filters; there is nothing to summarize yet."

    parts: list[str] = [
        f"Out of {total} execution attempt(s), {success} succeeded",
    ]
    if failure:
        parts.append(f" and {failure} did not")
    parts.append(".")
    sentence = "".join(parts)

    # Failure-oriented kinds (exclude success bucket from \"failure causes\")
    failure_counts = {
        k: v
        for k, v in by_type.items()
        if k != "execution_succeeded" and int(v) > 0
    }
    if failure_counts:
        ranked = sorted(failure_counts.items(), key=lambda x: -x[1])
        desc = ", ".join(
            f"{n} {_label_failure_kind(k)}" for k, n in ranked
        )
        sentence += f" Failures were primarily associated with: {desc}."
    elif failure == 0:
        sentence += " There were no failures in this scope."

    return sentence
