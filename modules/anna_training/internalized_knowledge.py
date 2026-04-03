"""When all Grade-12 curriculum skills are attested, snapshot them as internalized knowledge.

``grade_12_tool_mastery`` is the checklist; this layer records that the full set is now treated as
durable operating knowledge merged into carry-forward FACT lines for Anna's analyst path.
"""

from __future__ import annotations

from typing import Any

from modules.anna_training.curriculum_tools import (
    GRADE_12_TOOLS,
    curriculum_tools_complete,
    normalize_tool_mastery,
)
from modules.anna_training.cumulative import append_cumulative_log
from modules.anna_training.store import utc_now_iso


def maybe_grade12_internalize(state: dict[str, Any]) -> bool:
    """
    If all four tools are passed and we have not yet stamped internalization, set
    ``grade_12_knowledge_internalized``, append carryforward bullets, and log once.

    Idempotent: does nothing if ``grade_12_knowledge_internalized`` is already set.
    Returns True if this call performed the snapshot.
    """
    m = normalize_tool_mastery(state.get("grade_12_tool_mastery"))
    if not curriculum_tools_complete(m):
        return False
    if state.get("grade_12_knowledge_internalized"):
        return False

    now = utc_now_iso()
    state["grade_12_knowledge_internalized"] = {
        "version": 1,
        "at_utc": now,
        "skills": [
            {"id": t["id"], "title": t["title"], "summary": t["summary"]} for t in GRADE_12_TOOLS
        ],
    }

    bullets = list(state.get("carryforward_bullets") or [])
    summary_line = (
        "Grade 12 curriculum internalized (durable operating knowledge): "
        + "; ".join(t["title"] for t in GRADE_12_TOOLS)
        + ". These habits are cumulative FACT for analysis and the paper harness."
    )
    if summary_line not in bullets:
        bullets.append(summary_line)
    for t in GRADE_12_TOOLS:
        line = f"[INTERNALIZED G12] {t['id']}: {t['summary']}"
        if line not in bullets:
            bullets.append(line)
    state["carryforward_bullets"] = bullets

    append_cumulative_log(
        state,
        kind="grade_12_knowledge_internalized_v1",
        summary="All four Grade-12 skills recorded as internalized knowledge (carryforward + state snapshot).",
        curriculum_id=state.get("curriculum_id"),
        meta={"version": 1, "at_utc": now},
    )
    return True


def internalized_grade12_snapshot(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the internalization record if present (for status JSON / tooling)."""
    if not state:
        return None
    raw = state.get("grade_12_knowledge_internalized")
    return raw if isinstance(raw, dict) else None
