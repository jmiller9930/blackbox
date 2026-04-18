"""Parallel pattern-game batch (process pool)."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel


def _manifest() -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"


def test_run_scenarios_parallel_two_workers() -> None:
    m = _manifest()
    if not m.is_file():
        pytest.skip("baseline manifest missing")
    scenarios = [
        {"scenario_id": "parallel_a", "manifest_path": str(m)},
        {"scenario_id": "parallel_b", "manifest_path": str(m)},
    ]
    results = run_scenarios_parallel(scenarios, max_workers=2, experience_log_path=None)
    assert len(results) == 2
    for r in results:
        assert r.get("ok") is True
        assert r.get("summary") is not None


def test_run_scenarios_parallel_empty() -> None:
    assert run_scenarios_parallel([], max_workers=4) == []
