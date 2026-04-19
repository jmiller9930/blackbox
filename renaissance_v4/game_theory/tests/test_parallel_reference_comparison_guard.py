"""Batch guard for Reference Comparison Run (candidate search must execute)."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.parallel_runner import (
    REFERENCE_COMPARISON_RECIPE_ID,
    validate_reference_comparison_batch_results,
)


def test_validate_reference_comparison_ok_when_not_recipe() -> None:
    validate_reference_comparison_batch_results(
        [{"ok": True, "learning_run_audit_v1": {}}],
        operator_recipe_id="pattern_learning",
    )


def test_validate_reference_comparison_raises_when_zero_candidates() -> None:
    row = {
        "ok": True,
        "scenario_id": "s1",
        "learning_run_audit_v1": {
            "context_candidate_search_block_v1": {
                "context_candidate_search_ran": True,
                "candidate_count": 0,
            }
        },
    }
    with pytest.raises(RuntimeError, match="reference_comparison_invalid"):
        validate_reference_comparison_batch_results(
            [row], operator_recipe_id=REFERENCE_COMPARISON_RECIPE_ID
        )


def test_validate_reference_comparison_passes_with_candidates() -> None:
    row = {
        "ok": True,
        "scenario_id": "s1",
        "learning_run_audit_v1": {
            "context_candidate_search_block_v1": {
                "context_candidate_search_ran": True,
                "candidate_count": 4,
            }
        },
    }
    validate_reference_comparison_batch_results(
        [row], operator_recipe_id=REFERENCE_COMPARISON_RECIPE_ID
    )
