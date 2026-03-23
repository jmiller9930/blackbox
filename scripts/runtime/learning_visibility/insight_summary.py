"""Aggregate counts from insight rows (summary data for reports — not raw SQL)."""
from __future__ import annotations

from typing import Any


def summarize_insights(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build summary dict: total, success, failure, by_type (insight_kind → count).

    Expects rows shaped like `fetch_insights` output.
    """
    total = len(rows)
    success = 0
    failure = 0
    by_type: dict[str, int] = {}
    for row in rows:
        ins = row.get("insight") or {}
        kind = str(ins.get("insight_kind") or "unknown")
        by_type[kind] = by_type.get(kind, 0) + 1
        if ins.get("type") == "success":
            success += 1
        else:
            failure += 1
    return {
        "total": total,
        "success": success,
        "failure": failure,
        "by_type": by_type,
    }
