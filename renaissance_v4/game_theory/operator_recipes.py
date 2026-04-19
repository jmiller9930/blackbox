"""
Curated operator **recipes** for the pattern-game UI — small playbook set, not a glob of files.

Each recipe loads scenario JSON from ``game_theory/examples/`` and adds explicit metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_GAME_THEORY = Path(__file__).resolve().parent

# Source files (scenario batches only — not templates or memory-bundle artifacts).
_PATTERN_LEARNING_FILE = "tier1_twelve_month.example.json"
_REFERENCE_COMPARISON_FILE = "parallel_scenarios.example.json"

_GOAL_V2_PATTERN_OUTCOME_QUALITY: dict[str, Any] = {
    "goal_name": "pattern_outcome_quality",
    "objective_type": "outcome_quality",
    "primary_metric": "expectancy_per_trade",
    "secondary_metrics": [
        "avg_win_size",
        "avg_loss_size",
        "win_loss_size_ratio",
        "exit_efficiency",
    ],
    "constraints": {"minimum_trade_count": 5, "maximum_drawdown_threshold": None},
    "notes": {
        "intent_plain": (
            "Improve pattern recognition so trade outcomes are higher quality — not maximizing raw "
            "win count or a fixed PnL."
        ),
        "emphasis": "Outcome quality from pattern-aware behavior; engine stays neutral.",
    },
}


def _examples_path(name: str) -> Path:
    return _GAME_THEORY / "examples" / name


def _load_scenario_list(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("scenarios"), list):
        return [x for x in raw["scenarios"] if isinstance(x, dict)]
    raise ValueError(f"Expected scenario array in {path}")


def policy_catalog() -> list[dict[str, Any]]:
    """
    Selectable policies / manifests for the operator UI.

    When only one entry exists, the UI may show it read-only. Multiple entries enable a dropdown.
    """
    return [
        {
            "policy_id": "baseline_v1_recipe",
            "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
            "display_label": "baseline_v1_recipe (default)",
        },
    ]


def operator_recipe_catalog() -> list[dict[str, Any]]:
    """
    Static metadata for ``GET /api/operator-recipes``.

    ``default_evaluation_window_months`` — used only for override bookkeeping in the UI merge;
    the operator **always** selects a window mode explicitly (default 12 in the UI).

    ``goal_summary`` — operator-facing read-only lines (no need to edit JSON).
    """
    return [
        {
            "recipe_id": "pattern_learning",
            "operator_label": "Pattern Learning Run",
            "operator_visible": True,
            "category": "primary",
            "experiment_type": "single_run",
            "comparison_mode": False,
            "default_evaluation_window_months": 12,
            "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
            "goal_v2": _GOAL_V2_PATTERN_OUTCOME_QUALITY,
            "goal_summary": {
                "title": "Pattern Outcome Quality",
                "goal_name": "pattern_outcome_quality",
                "primary_metric": "expectancy_per_trade",
                "constraints_line": "Minimum 5 trades; max drawdown threshold unset.",
                "note": "Optimizes outcome-quality metrics — not a fixed PnL or win-rate target.",
            },
            "scenario_count": 1,
            "source_file": _PATTERN_LEARNING_FILE,
        },
        {
            "recipe_id": "reference_comparison",
            "operator_label": "Reference Comparison Run",
            "operator_visible": True,
            "category": "reference",
            "experiment_type": "comparison_batch",
            "comparison_mode": True,
            "default_evaluation_window_months": 12,
            "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
            "goal_v2": None,
            "goal_summary": {
                "title": "Reference comparison",
                "goal_name": "—",
                "primary_metric": "—",
                "constraints_line": "Three scenarios: default vs tighter vs wider ATR (same manifest).",
                "note": "No goal_v2 block — session economics and Referee scorecard only.",
            },
            "scenario_count": 3,
            "source_file": _REFERENCE_COMPARISON_FILE,
        },
    ]


def recipe_meta_by_id(recipe_id: str) -> dict[str, Any] | None:
    for row in operator_recipe_catalog():
        if row["recipe_id"] == recipe_id:
            return row
    return None


def build_scenarios_for_recipe(recipe_id: str) -> list[dict[str, Any]]:
    """
    Return a **fresh** list of scenario dicts for the curated recipe (deep copies safe for merge).
    """
    meta = recipe_meta_by_id(recipe_id)
    if meta is None:
        raise ValueError(f"unknown operator recipe_id: {recipe_id!r}")

    path = _examples_path(str(meta["source_file"]))
    if not path.is_file():
        raise FileNotFoundError(f"operator recipe source missing: {path}")

    scenarios = _load_scenario_list(path)
    out: list[dict[str, Any]] = [copy_scenario(s) for s in scenarios]

    if recipe_id == "pattern_learning":
        for s in out:
            s["goal_v2"] = json.loads(json.dumps(_GOAL_V2_PATTERN_OUTCOME_QUALITY))

    return out


def copy_scenario(s: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(s))


def default_recipe_id() -> str:
    return "pattern_learning"
