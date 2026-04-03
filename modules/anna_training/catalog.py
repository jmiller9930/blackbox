"""Built-in curricula and training methods (v1 — no DB required)."""

from __future__ import annotations

from typing import Any

# CONTRACT: "12th grade" curriculum id and Karpathy method ids are canonical — keep in sync with
# docs/architect/ANNA_GOES_TO_SCHOOL.md §1.1, §1.2, and §3. Loop steps below MUST match §3 numbering (7 steps).
CURRICULA: dict[str, dict[str, Any]] = {
    "grade_12_paper_only": {
        "title": "Grade 12 equivalent — paper trading only",
        "stage": "secondary",
        "harness": "paper_loop_and_simulation",
        "live_venue_execution": False,
        "contract_doc": "docs/architect/ANNA_GOES_TO_SCHOOL.md §1.1 §1.2",
        "next_curriculum_id": "bachelor_paper_track_v1",
        "summary": (
            "Anna trains against approved paper/simulation paths only; "
            "no Billy/Jack live submits until human graduation policy says otherwise."
        ),
    },
    "bachelor_paper_track_v1": {
        "title": "Bachelor track — paper trading (cumulative with Grade 12)",
        "stage": "bachelor",
        "harness": "paper_loop_and_simulation",
        "live_venue_execution": False,
        "prerequisite_curriculum_id": "grade_12_paper_only",
        "requires_grade12_numeric_gate": True,
        "contract_doc": "docs/architect/ANNA_GOES_TO_SCHOOL.md + modules/anna_training/cumulative.py",
        "summary": (
            "Continues Karpathy measurement on paper; all validated Grade 12 habits, math-engine literacy, "
            "and cohort history are cumulative — deeper analysis, same harness constraints until policy changes."
        ),
    },
}

# Karpathy-aligned loop — steps MUST mirror ANNA_GOES_TO_SCHOOL.md §3 (1–7). Do not merge or reorder
# without updating the doc in the same commit.
TRAINING_METHODS: dict[str, dict[str, Any]] = {
    "karpathy_loop_v1": {
        "title": "Karpathy-aligned training loop (BLACK BOX v1)",
        "steps": [
            "Ingest curriculum, baseline doctrine, fresh approved data, and governed human direction",
            "Generate a candidate insight, strategy, correction, or action proposal",
            "Test it in the allowed harness",
            "Measure outcome against explicit gates",
            "Keep what works",
            "Drop what does not work",
            "Repeat continuously",
        ],
        "reference": "docs/architect/ANNA_GOES_TO_SCHOOL.md §3",
    },
}

# Full University methodology matrix (RAG, bandits, Bayesian optimization, walk-forward, etc.) lives in
# docs/architect/anna_university_methodology.md — not all are selectable CLI methods; Karpathy remains primary ID.
UNIVERSITY_METHODOLOGY_CANON: dict[str, str] = {
    "anna_methodology_doc": "docs/architect/anna_university_methodology.md",
    "platform_university_doc": "docs/architect/blackbox_university.md",
    "staging_subtree_readme": "university/README.md",
    "methods_notes_staging": "university/docs/METHODS_NOTES.md",
}

# Not separate invoke IDs — nested inside Karpathy steps 4–7 / paper harness. Exposed for operator JSON.
COMPLEMENTARY_PEDAGOGY: list[dict[str, str]] = [
    {
        "id": "cumulative_learning_carryforward",
        "title": "Cumulative learning — Grade 12 → bachelor; carryforward_bullets + cumulative_learning_log in state.json",
        "reference": "modules/anna_training/cumulative.py + progression.py",
        "note": "Merged as FACT (cumulative learning) in analyst path when carryforward_bullets present",
    },
    {
        "id": "anna_math_analysis_pedagogy",
        "title": "How Anna uses the math engine — LLM procedure (cite FACT lines, no invented stats, uncertainty when n small)",
        "reference": "scripts/runtime/anna_modules/analysis_math_pedagogy.py + llm/prompt_builder.py + anna_modules/pipeline.py",
        "note": "Merged into every Anna LLM call as snippets + MATH ANALYSIS PROCEDURE block",
    },
    {
        "id": "training_quant_metrics_engine",
        "title": "Math engine quant layer — per-trade Sharpe/Sortino proxies, drawdown, Calmar, historical VaR/CVaR on paper P&L",
        "reference": "modules/anna_training/quant_metrics.py + scripts/runtime/anna_modules/analysis_math.py",
        "note": "Deterministic Python; `anna_training_cli.py quant-metrics`; merged into Anna AUTHORITATIVE FACTS when paper trades exist",
    },
    {
        "id": "math_engine_full_stack",
        "title": "Full quant stack — ARIMA/GARCH, annualized Sharpe+rf, walk-forward, Monte Carlo bootstrap, sklearn baseline, Kalman; Engle-Granger when aux series provided",
        "reference": "modules/anna_training/math_engine_full/ + requirements.txt (numpy, pandas, statsmodels, arch, scikit-learn)",
        "note": "Analyst merge gated by ANNA_MATH_ENGINE_FULL=1; run `anna_training_cli.py math-engine-full` anytime",
    },
    {
        "id": "core_learning_loop_lock",
        "title": "Observe → thesis → act → measure → lightweight why → keep / watch / drop",
        "reference": "docs/architect/ANNA_GOES_TO_SCHOOL.md §3.1 (core learning loop lock)",
        "note": "RCS cadence; not a replacement for karpathy_loop_v1",
    },
    {
        "id": "reflection_rcs_rca_dna",
        "title": "Win/loss interrogation; qualifying failures → RCA; repeat-failure escalation",
        "reference": "docs/architect/ANNA_GOES_TO_SCHOOL.md §3.3",
        "note": "Artifact shapes when persisted; complements Karpathy measurement step",
    },
    {
        "id": "bayesian_optimization_safe_strategy_tuning",
        "title": "Bayesian optimization under hard constraints (safe strategy parameter search)",
        "reference": "docs/architect/anna_university_methodology.md (Architect Handoff table — Safe strategy tuning row)",
        "note": "University matrix item; not a separate anna_training_cli method id in v1",
    },
    {
        "id": "university_explicit_cs_methodologies_1_18",
        "title": "Explicit CS methodologies list (RAG, distillation, bandits, CMDP, calibration, …)",
        "reference": "docs/architect/anna_university_methodology.md § Explicit Computer Science Methodologies",
        "note": "Platform-wide design references; implementation is phased per development_plan 5.8",
    },
]


def default_state() -> dict[str, Any]:
    from modules.anna_training.curriculum_tools import default_grade_12_tool_mastery

    return {
        "schema_version": "anna_training_state_v3",
        "curriculum_id": None,
        "training_method_id": None,
        "method_invoked_at_utc": None,
        "curriculum_assigned_at_utc": None,
        "operator_notes": [],
        "completed_curriculum_milestones": [],
        "cumulative_learning_log": [],
        "carryforward_bullets": [],
        "bachelor_track_started_at_utc": None,
        "grade_12_tool_mastery": default_grade_12_tool_mastery(),
    }


def describe_catalog() -> dict[str, Any]:
    return {
        "curricula": {k: {**v, "id": k} for k, v in CURRICULA.items()},
        "methods": {k: {**v, "id": k} for k, v in TRAINING_METHODS.items()},
        "complementary_pedagogy": COMPLEMENTARY_PEDAGOGY,
        "university_methodology_canon": UNIVERSITY_METHODOLOGY_CANON,
        "primary_method_id": "karpathy_loop_v1",
    }
