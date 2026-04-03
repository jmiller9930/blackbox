"""Grade 12 curriculum — four named learning outcomes / processes (not arbitrary flags).

Each id is something Anna must learn and apply; software stores binary attestation after evidence.
All four true before the numeric paper gate counts. See ANNA_GOES_TO_SCHOOL.md §1.3."""

from __future__ import annotations

from typing import Any, Mapping

# Strict sequence: each skill builds on the last; complete in order before the paper cohort gate.
# Order: numeracy → analysis → RCS/RCA → harness loop → then numeric paper trading bar applies.
GRADE_12_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "id": "math_engine_literacy",
        "title": "Math engine literacy",
        "summary": "Cite FACT lines only; epistemic honesty; Wilson/NIST checks when claiming numbers.",
        "education_benchmark": {
            "id": "wilson_nist_reference_v1",
            "summary": (
                "All NIST-style Wilson cases pass: float `wilson_score_interval_95` vs independent "
                "Decimal oracle for every row in `WILSON_NIST_CASES` (see `wilson_nist_reference.py`)."
            ),
            "predicate_hook": "run_wilson_reference_check()['ok'] === true",
            "cli_verify": "anna math-check",
        },
    },
    {
        "id": "analysis_algorithms",
        "title": "Analysis & algorithms",
        "summary": "Apply quant stack (metrics, pedagogy path) — separate noise from signal per harness.",
        "education_benchmark": {
            "id": "paper_quant_metrics_v1",
            "summary": "At least one paper trade exists and `compute_paper_quant_metrics` runs successfully on the cohort.",
            "predicate_hook": "len(paper_trades) >= 1 and metrics computed",
            "cli_verify": "anna quant-metrics",
        },
    },
    {
        "id": "rcs_rca_discipline",
        "title": "RCS / RCA discipline",
        "summary": "Win/loss interrogation; qualifying failures → RCA; traceable thesis ↔ outcome.",
        "education_benchmark": {
            "id": "paper_trade_reflection_note_v1",
            "summary": "At least one logged paper trade has a non-empty `notes` field (reflection habit).",
            "predicate_hook": "count(trades with notes) >= 1",
            "cli_verify": "anna log-trade ... (include notes) / inspect paper_trades.jsonl",
        },
    },
    {
        "id": "karpathy_harness_loop",
        "title": "Karpathy harness loop",
        "summary": "Paper harness: propose → test → measure → keep/drop → repeat until gates.",
        "education_benchmark": {
            "id": "karpathy_iteration_threshold_v1",
            "summary": "`karpathy_loop_iteration` in state meets `ANNA_KARPATHY_HARNESS_MIN_ITERATIONS` (default 10).",
            "predicate_hook": "state.karpathy_loop_iteration >= ANNA_KARPATHY_HARNESS_MIN_ITERATIONS",
            "cli_verify": "anna status (iteration field) / loop heartbeats",
        },
    },
)

TOOL_IDS: tuple[str, ...] = tuple(str(t["id"]) for t in GRADE_12_TOOLS)


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


def tool_meta(tool_id: str) -> dict[str, Any] | None:
    for t in GRADE_12_TOOLS:
        if t["id"] == tool_id:
            return dict(t)
    return None


def build_grade12_skills_deck(state: Mapping[str, Any], g12: Mapping[str, Any]) -> dict[str, Any]:
    """Snapshot for state + logs: ordered requirements, current focus, completion flags."""
    mastery = normalize_tool_mastery(state.get("grade_12_tool_mastery"))
    missing = missing_grade_12_tools(mastery)
    if missing:
        current_focus = missing[0]
    elif not g12.get("numeric_gate_pass"):
        current_focus = "numeric_paper_cohort"
    elif g12.get("pass"):
        current_focus = "grade_12_gate_complete"
    else:
        current_focus = "numeric_paper_cohort"
    tools = [{"id": t["id"], "title": t["title"], "passed": bool(mastery.get(t["id"]))} for t in GRADE_12_TOOLS]
    tools_complete = curriculum_tools_complete(mastery)
    deck_complete = bool(g12.get("pass"))
    return {
        "version": 1,
        "karpathy_loop_iteration": state.get("karpathy_loop_iteration"),
        "current_focus_requirement": current_focus,
        "tools": tools,
        "tools_complete": tools_complete,
        "numeric_gate_pass": bool(g12.get("numeric_gate_pass")),
        "overall_gate_pass": bool(g12.get("pass")),
        "deck_complete": deck_complete,
    }
