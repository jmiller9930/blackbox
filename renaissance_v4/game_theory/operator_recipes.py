"""
Curated operator **recipes** for the pattern-game UI — small playbook set, not a glob of files.

Each recipe loads scenario JSON from ``game_theory/examples/`` and adds explicit metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.scenario_contract import resolve_scenario_manifest_path

_GAME_THEORY = Path(__file__).resolve().parent

# Source files (scenario batches only — not templates or memory-bundle artifacts).
_PATTERN_LEARNING_FILE = "tier1_twelve_month.example.json"
_REFERENCE_COMPARISON_FILE = "parallel_scenarios.example.json"

# Default bounded behavior space for baseline v1 (manifest remains execution source).
_DEFAULT_POLICY_FRAMEWORK_PATH = (
    "renaissance_v4/configs/manifests/baseline_v1_policy_framework.json"
)

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
            "policy_framework_path": _DEFAULT_POLICY_FRAMEWORK_PATH,
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
            "operator_label": "Pattern Machine Learning (PML)",
            "operator_visible": True,
            "category": "primary",
            "experiment_type": "single_run",
            "comparison_mode": False,
            "default_evaluation_window_months": 12,
            "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
            "policy_framework_path": _DEFAULT_POLICY_FRAMEWORK_PATH,
            "goal_v2": _GOAL_V2_PATTERN_OUTCOME_QUALITY,
            "goal_summary": {
                "title": "Pattern Outcome Quality",
                "goal_name": "pattern_outcome_quality",
                "primary_metric": "expectancy_per_trade",
                "constraints_line": "Minimum 5 trades; max drawdown threshold unset.",
                "note": (
                    "Runs operator_test_harness_v1: bounded candidate search vs control on the baseline "
                    "manifest inside the policy framework tunable surface; scorecard Cand/Learn reflect harness output."
                ),
            },
            "operator_mode_card_v1": {
                "title": "Pattern Machine Learning (PML)",
                "sections": [
                    {
                        "k": "What this does",
                        "v": (
                            "This run is trying to find a better version of your strategy.\n\n"
                            "It does this by:\n\n"
                            "* running the baseline strategy\n"
                            "* trying many small variations\n"
                            "* checking if anything performs better"
                        ),
                    },
                    {
                        "k": "What happens during the run",
                        "v": (
                            "For each scenario:\n\n"
                            "* the system runs the baseline (control)\n"
                            "* then it tests multiple variations (candidates)\n"
                            "* it compares results\n"
                            "* if something is better, it becomes the winner"
                        ),
                    },
                    {
                        "k": "What you get",
                        "v": (
                            "At the end, you'll see:\n\n"
                            "* whether a better version was found\n"
                            "* which variation won\n"
                            "* how much better it performed"
                        ),
                    },
                    {
                        "k": "Memory (this is the important part)",
                        "v": (
                            "This is where learning actually happens.\n\n"
                            "If Learning Mode = READ+WRITE:\n\n"
                            "* the system saves the winner\n"
                            "* future runs can use that knowledge\n\n"
                            "If READ only:\n\n"
                            "* it uses past learning\n"
                            "* but does not learn anything new\n\n"
                            "If OFF:\n\n"
                            "* no memory is used\n"
                            "* every run starts from scratch"
                        ),
                    },
                    {
                        "k": 'What "learning" actually means here',
                        "v": (
                            "* the system remembers what worked before\n"
                            "* when it sees a similar situation again\n"
                            "* it can bias decisions toward that winner\n\n"
                            "Think:\n"
                            '"I\'ve seen this before — do more of what worked"'
                        ),
                    },
                    {
                        "k": "What it does NOT do",
                        "v": (
                            "* it does NOT automatically change your live strategy\n"
                            "* it does NOT persist anything unless learning is ON\n"
                            "* it does NOT guarantee a winner every run"
                        ),
                    },
                    {
                        "k": "When to use this",
                        "v": (
                            'Use this when you want to answer:\n\n'
                            '"Can the system find a better version of this strategy?"'
                        ),
                    },
                    {
                        "k": "One-line summary",
                        "v": (
                            "This run searches for better strategy variations and, if learning is ON, "
                            "remembers what works so future runs can improve."
                        ),
                    },
                ],
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
            "policy_framework_path": _DEFAULT_POLICY_FRAMEWORK_PATH,
            "goal_v2": None,
            "goal_summary": {
                "title": "Reference comparison",
                "goal_name": "—",
                "primary_metric": "—",
                "constraints_line": "Three scenarios: default vs tighter vs wider ATR (same manifest).",
                "note": (
                    "Parallel workers run operator_test_harness_v1 (context-conditioned candidate search "
                    "with control + candidates). Scorecard Cand/Learn reflect that path; zero candidates fails the run."
                ),
            },
            "operator_mode_card_v1": {
                "title": "Reference Comparison Run",
                "sections": [
                    {
                        "k": "What this does",
                        "v": (
                            "This run tests three versions of the same strategy at the same time:\n\n"
                            "* Default settings\n"
                            "* Tighter risk (smaller stops and targets)\n"
                            "* Wider risk (larger stops and targets)\n\n"
                            "All three are run on the same data so you can see which one performs better."
                        ),
                    },
                    {
                        "k": "What happens during the run",
                        "v": (
                            "For each version:\n\n"
                            "* the system runs the baseline strategy\n"
                            "* then it tries small variations (candidates)\n"
                            "* it checks if any variation beats the baseline"
                        ),
                    },
                    {
                        "k": "What you get",
                        "v": (
                            "At the end, you'll see:\n\n"
                            "* which version performed best\n"
                            "* whether any improvement was found\n"
                            "* a winner if something beat the baseline"
                        ),
                    },
                    {
                        "k": "Important things to know",
                        "v": (
                            "* each version is tested independently\n"
                            "* this is a comparison, not a replacement\n"
                            "* nothing is saved automatically"
                        ),
                    },
                    {
                        "k": "Memory (learning)",
                        "v": (
                            "* memory is only used if you turn it on\n"
                            "* if a winner is found, it can be saved\n"
                            "* nothing is carried forward unless you explicitly keep it"
                        ),
                    },
                    {
                        "k": "When to use this",
                        "v": (
                            'Use this run when you want to answer:\n\n'
                            '"Do tighter trades, wider trades, or default settings work best right now?"'
                        ),
                    },
                    {
                        "k": "One-line summary",
                        "v": (
                            "This run compares tight vs normal vs wide risk settings and tells you which one "
                            "performs best — nothing changes unless you choose to keep it."
                        ),
                    },
                ],
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

    for s in out:
        mp = s.get("manifest_path")
        if isinstance(mp, str) and mp.strip():
            s["manifest_path"] = str(resolve_scenario_manifest_path(mp))

    pfw = meta.get("policy_framework_path")
    if isinstance(pfw, str) and pfw.strip():
        for s in out:
            s["policy_framework_path"] = pfw.strip()

    if recipe_id == "pattern_learning":
        for s in out:
            s["goal_v2"] = json.loads(json.dumps(_GOAL_V2_PATTERN_OUTCOME_QUALITY))

    return out


def copy_scenario(s: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(s))


def default_recipe_id() -> str:
    return "pattern_learning"
