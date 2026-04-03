"""Cumulative learning: carry-forward state, fact lines for Anna, promotion helpers."""

from __future__ import annotations

from typing import Any

from modules.anna_training.store import utc_now_iso


def default_carryforward_bullets() -> list[str]:
    return [
        "Grade 12 paper harness: RCS/RCA discipline, Wilson-backed cohort stats, and explicit gates carry forward.",
        "Math engine literacy: cite FACT lines only; epistemic honesty when evidence is thin carries forward.",
        "Karpathy loop habit — measure, keep/drop, repeat — is cumulative across curriculum stages.",
    ]


def append_cumulative_log(
    state: dict[str, Any],
    *,
    kind: str,
    summary: str,
    curriculum_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    log = list(state.get("cumulative_learning_log") or [])
    row: dict[str, Any] = {
        "ts_utc": utc_now_iso(),
        "kind": kind,
        "curriculum_id": curriculum_id,
        "summary": (summary or "")[:2000],
    }
    if meta:
        row["meta"] = meta
    log.append(row)
    state["cumulative_learning_log"] = log[-500:]
    return state


def record_curriculum_milestone(state: dict[str, Any], curriculum_id: str) -> dict[str, Any]:
    m = list(state.get("completed_curriculum_milestones") or [])
    if curriculum_id and curriculum_id not in m:
        m.append(curriculum_id)
    state["completed_curriculum_milestones"] = m
    return state


def promote_to_bachelor_track(state: dict[str, Any]) -> dict[str, Any]:
    """Set bachelor curriculum and seed carry-forward bullets (idempotent merge)."""
    record_curriculum_milestone(state, "grade_12_paper_only")
    bullets = list(state.get("carryforward_bullets") or [])
    for b in default_carryforward_bullets():
        if b not in bullets:
            bullets.append(b)
    state["carryforward_bullets"] = bullets
    state["curriculum_id"] = "bachelor_paper_track_v1"
    state["curriculum_assigned_at_utc"] = utc_now_iso()
    state["bachelor_track_started_at_utc"] = utc_now_iso()
    append_cumulative_log(
        state,
        kind="promoted_to_bachelor_paper_track_v1",
        summary="Cumulative learning from Grade 12 retained; bachelor paper track active.",
        curriculum_id="bachelor_paper_track_v1",
    )
    return state


def carryforward_fact_lines(state: dict[str, Any] | None) -> list[str]:
    """Authoritative FACT lines for LLM merge (short).

    Injected on every analyst path (see ``analysis.build_analysis``) — Anna does not need to ask
    for these; they are always part of ``facts_for_prompt`` when state is loadable.
    """
    if not state:
        return []
    bullets = list(state.get("carryforward_bullets") or [])
    if not bullets:
        return []
    lines: list[str] = []
    for b in bullets[:12]:
        lines.append(f"FACT (cumulative learning): {b}")
    return lines
