"""Grade 12 required tools — must be passed (cohesive set) before numeric gate / revenue bar counts."""

from __future__ import annotations

from typing import Any

# Ordered checklist: learn each tool, then use them together; then 60% / fund objectives apply.
GRADE_12_TOOLS: tuple[dict[str, str], ...] = (
    {
        "id": "math_engine_literacy",
        "title": "Math engine literacy",
        "summary": "Cite FACT lines only; epistemic honesty; Wilson/NIST checks when claiming numbers.",
    },
    {
        "id": "analysis_algorithms",
        "title": "Analysis & algorithms",
        "summary": "Apply quant stack (metrics, pedagogy path) — separate noise from signal per harness.",
    },
    {
        "id": "rcs_rca_discipline",
        "title": "RCS / RCA discipline",
        "summary": "Win/loss interrogation; qualifying failures → RCA; traceable thesis ↔ outcome.",
    },
    {
        "id": "karpathy_harness_loop",
        "title": "Karpathy harness loop",
        "summary": "Paper harness: propose → test → measure → keep/drop → repeat until gates.",
    },
)

TOOL_IDS: tuple[str, ...] = tuple(t["id"] for t in GRADE_12_TOOLS)


def default_grade_12_tool_mastery() -> dict[str, bool]:
    return {tid: False for tid in TOOL_IDS}


def normalize_tool_mastery(raw: Any) -> dict[str, bool]:
    """Merge saved state with canonical keys (new tools default False)."""
    base = default_grade_12_tool_mastery()
    if isinstance(raw, dict):
        for k in TOOL_IDS:
            if k in raw:
                base[k] = bool(raw[k])
    return base


def curriculum_tools_complete(mastery: dict[str, bool] | None) -> bool:
    m = normalize_tool_mastery(mastery)
    return all(m.get(tid) for tid in TOOL_IDS)


def missing_grade_12_tools(mastery: dict[str, bool] | None) -> list[str]:
    m = normalize_tool_mastery(mastery)
    return [tid for tid in TOOL_IDS if not m.get(tid)]


def tool_meta(tool_id: str) -> dict[str, str] | None:
    for t in GRADE_12_TOOLS:
        if t["id"] == tool_id:
            return dict(t)
    return None
