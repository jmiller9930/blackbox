"""
Operator-facing **surface catalog** for Ask DATA — generated from code + limits, not hand-edited HTML.

Single source for ``sanitize_ui_context`` allowed keys and for ``operator_surface_catalog`` in the bundle.
"""

from __future__ import annotations

from typing import Any

def downloadable_operator_artifacts_v1() -> list[dict[str, Any]]:
    """
    Operator-facing **download / export** routes (Pattern Game Flask).

    Keep in sync with ``web_app.py``; Ask DATA uses this to point operators at real clicks or URLs
    instead of inventing files.
    """
    return [
        {
            "id": "batch_scorecard_history_csv",
            "method": "GET",
            "path": "/api/batch-scorecard.csv",
            "query_params": "limit (optional, e.g. 50)",
            "attachment": True,
            "mime": "text/csv",
            "ui_anchor": "Download scorecard history (CSV) — `scorecardCsvLink` on operator page when rendered",
        },
        {
            "id": "batch_detail_scenarios_csv",
            "method": "GET",
            "path": "/api/batch-detail.csv",
            "query_params": "job_id=<parallel_job_id> (required)",
            "attachment": True,
            "mime": "text/csv",
            "ui_anchor": "Per-batch drill UI may append “Download this batch (CSV)” when a row is selected",
        },
        {
            "id": "training_dataset_ndjson",
            "method": "GET",
            "path": "/api/training/export",
            "query_params": "download=1 for attachment; preview=N (default 5) for JSON preview body",
            "attachment_query": "download=1",
            "mime": "application/x-ndjson",
            "directive": "GT_DIRECTIVE_022",
        },
        {
            "id": "training_dataset_materialize",
            "method": "POST",
            "path": "/api/training/export/materialize",
            "body": "JSON with typed confirm phrase (see API) — writes default training_dataset_v1.jsonl path in response",
            "attachment": False,
            "directive": "GT_DIRECTIVE_022",
        },
        {
            "id": "learning_effectiveness_report_json",
            "method": "GET",
            "path": "/api/training/learning-effectiveness",
            "query_params": "summary=1 for smaller JSON",
            "attachment": False,
            "directive": "GT_DIRECTIVE_023",
        },
        {
            "id": "learning_effectiveness_materialize",
            "method": "POST",
            "path": "/api/training/learning-effectiveness/materialize",
            "body": "JSON with typed confirm — writes learning_effectiveness_report_v1.json",
            "attachment": False,
            "directive": "GT_DIRECTIVE_023",
        },
        {
            "id": "learning_flow_validate",
            "method": "GET",
            "path": "/api/training/learning-flow-validate",
            "query_params": "run_a, run_b = job_id",
            "attachment": False,
            "directive": "GT_DIRECTIVE_025",
        },
        {
            "id": "learning_flow_validate_materialize",
            "method": "POST",
            "path": "/api/training/learning-flow-validate/materialize",
            "body": "JSON: run_a, run_b, confirm=MATERIALIZE_LEARNING_FLOW_VALIDATION_V1",
            "attachment": False,
            "directive": "GT_DIRECTIVE_025",
        },
        {
            "id": "trade_strategy_json_export",
            "method": "GET",
            "path": "/api/v1/trade-strategy/<strategy_id>/export",
            "query_params": "strategy_id in path",
            "attachment": True,
            "note": "DEV stub — portable trade_strategy JSON when implemented",
        },
    ]


ASK_DATA_UI_CONTEXT_ALLOWED: frozenset[str] = frozenset(
    {
        "operator_recipe_id",
        "evaluation_window_mode",
        "evaluation_window_custom_months",
        "context_signature_memory_mode",
        "use_operator_uploaded_strategy",
        "scenarios_source",
        "recipe_label",
        "pattern_game_web_ui_version",
    }
)


def build_operator_surface_catalog_for_ask_v1() -> dict[str, Any]:
    """
    Machine-readable catalog of primary controls and limits.

    Extend here when new operator controls are added so Ask DATA stays aligned without scraping HTML.
    """
    from renaissance_v4.game_theory.operator_recipes import operator_recipe_catalog
    from renaissance_v4.game_theory.parallel_runner import get_parallel_limits

    lim = get_parallel_limits()
    recipes = operator_recipe_catalog()
    pattern_rows: list[dict[str, Any]] = []
    for r in recipes:
        if not isinstance(r, dict):
            continue
        if not r.get("operator_visible", True):
            continue
        pattern_rows.append(
            {
                "recipe_id": r.get("recipe_id"),
                "operator_label": r.get("operator_label"),
                "category": r.get("category"),
                "default_evaluation_window_months": r.get("default_evaluation_window_months"),
            }
        )

    return {
        "schema": "operator_surface_catalog_v1",
        "note": (
            "Controls are configured in the **operator UI** (Flask page). This object is **read-only** telemetry "
            "for Ask DATA — it does not change settings. Operators change values in Controls / Advanced; "
            "`ui_context` on each Ask DATA request echoes a **sanitized subset** (see `ask_data_ui_context_keys`)."
        ),
        "ask_data_ui_context_keys": sorted(ASK_DATA_UI_CONTEXT_ALLOWED),
        "parallel_limits": dict(lim),
        "evaluation_window": {
            "dom_id": "evaluationWindowPick",
            "options": [
                {"value": "12", "meaning": "approx_last_12_calendar_months_of_tape"},
                {"value": "18", "meaning": "approx_last_18_calendar_months_of_tape"},
                {"value": "24", "meaning": "approx_last_24_calendar_months_of_tape"},
                {"value": "custom", "meaning": "use_evaluationWindowCustomMonths_integer"},
            ],
            "custom_months_input": {"dom_id": "evaluationWindowCustomMonths", "min": 1, "max": 600},
        },
        "pattern_select": {
            "dom_id": "operatorRecipePick",
            "options": pattern_rows,
            "custom_json_note": "When Pattern is `custom`, scenarios come from the Custom scenario JSON path in Advanced.",
        },
        "workers": {
            "dom_id": "workersRange",
            "display_dom_id": "workersVal",
            "min": 1,
            "max_effective": "min(hard_cap_workers, scenario_count) at run time — see parallel_limits",
            "limits": {k: lim.get(k) for k in ("cpu_logical_count", "recommended_max_workers", "hard_cap_workers")},
        },
        "strategy_upload": {
            "toggle_dom_id": "useOperatorUploadedStrategy",
            "api_echo": "use_operator_uploaded_strategy + scenarios_source in ui_context",
            "operator_strategy_upload_state": "Separate bundle section — validation/path state from server.",
        },
        "exam_controls_primary": {
            "run_mode_dom_id": "examStudentReasoningModePick",
            "legacy_brain_profile_override_dom_id": "pgExamLegacyBrainProfileOverride",
            "student_brain_profile_dom_id": "examStudentReasoningModePick",
            "ollama_model_dom_id": "examLlmModelPick",
            "skip_cold_baseline_dom_id": "examSkipColdBaselineIfAnchor",
            "prompt_version_dom_id": "examPromptVersion",
            "run_button_dom_id": "runBtn",
            "note": "Primary operator selector is **Baseline** vs **Student**; `pgExamLegacyBrainProfileOverride` in Advanced is internal-only. Exam contract is sent on Run exam.",
        },
        "bar_tape": {
            "sqlite_table": "market_bars_5m",
            "row_interval": "5m_ohlc",
            "detail": "See `data_health_snapshot` in the Ask DATA bundle for counts and spans.",
        },
        "downloadable_artifacts": downloadable_operator_artifacts_v1(),
    }
