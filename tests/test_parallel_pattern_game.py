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


def test_run_scenarios_parallel_progress_callback() -> None:
    m = _manifest()
    if not m.is_file():
        pytest.skip("baseline manifest missing")
    seen: list[tuple[int, int, str]] = []

    def cb(completed: int, total: int, row: dict) -> None:
        seen.append((completed, total, str(row.get("scenario_id", ""))))

    scenarios = [
        {"scenario_id": "cb_a", "manifest_path": str(m)},
        {"scenario_id": "cb_b", "manifest_path": str(m)},
    ]
    run_scenarios_parallel(scenarios, max_workers=2, experience_log_path=None, progress_callback=cb)
    assert len(seen) == 2
    assert {x[0] for x in seen} == {1, 2}
    assert seen[0][1] == 2 and seen[1][1] == 2


def test_run_scenarios_parallel_echoes_agent_fields() -> None:
    m = _manifest()
    if not m.is_file():
        pytest.skip("baseline manifest missing")
    scenarios = [
        {
            "scenario_id": "with_agent",
            "manifest_path": str(m),
            "agent_explanation": {
                "why_this_strategy": "unit_test",
                "indicator_values": {"k": 1},
                "learned": "prior",
                "behavior_change": "nudge_stop",
            },
            "training_trace_id": "trace-1",
            "prior_scenario_id": "prev-0",
        }
    ]
    results = run_scenarios_parallel(scenarios, max_workers=1, experience_log_path=None)
    assert len(results) == 1
    r = results[0]
    assert r.get("ok") is True
    assert r.get("training_trace_id") == "trace-1"
    assert r.get("prior_scenario_id") == "prev-0"
    assert r.get("agent_explanation", {}).get("why_this_strategy") == "unit_test"


def test_run_scenarios_parallel_echoes_tier_and_window() -> None:
    m = _manifest()
    if not m.is_file():
        pytest.skip("baseline manifest missing")
    scenarios = [
        {
            "scenario_id": "tier1_echo",
            "manifest_path": str(m),
            "tier": "T1",
            "evaluation_window": {"calendar_months": 12},
            "game_spec_ref": "GAME_SPEC_INDICATOR_PATTERN_V1.md",
        }
    ]
    results = run_scenarios_parallel(scenarios, max_workers=1, experience_log_path=None)
    assert len(results) == 1
    r = results[0]
    assert r.get("ok") is True
    assert r.get("tier") == "T1"
    assert r.get("evaluation_window", {}).get("calendar_months") == 12
    assert "GAME_SPEC" in (r.get("game_spec_ref") or "")
