"""Scenario batch JSON validation helpers."""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.game_theory.scenario_contract import (
    extract_agent_fields,
    extract_scenario_echo_fields,
    validate_scenarios,
)


def test_validate_scenarios_requires_manifest_path() -> None:
    ok, msgs = validate_scenarios([{"scenario_id": "x"}])
    assert ok is False
    assert any("manifest_path" in m for m in msgs)


def test_validate_scenarios_warns_unknown_top_level_keys() -> None:
    root = Path(__file__).resolve().parents[1]
    mp = root / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not mp.is_file():
        return
    ok, msgs = validate_scenarios(
        [{"scenario_id": "a", "manifest_path": str(mp), "custom_ml_payload": {"x": 1}}]
    )
    assert ok is True
    assert any("undocumented" in m for m in msgs)


def test_extract_agent_fields_subset() -> None:
    d = extract_agent_fields(
        {
            "manifest_path": "/x",
            "agent_explanation": {"why_this_strategy": "q"},
            "training_trace_id": "t",
            "noise": 1,
        }
    )
    assert "noise" not in d
    assert d["training_trace_id"] == "t"
    assert d["agent_explanation"]["why_this_strategy"] == "q"


def test_validate_scenarios_require_hypothesis_blocks_empty() -> None:
    root = Path(__file__).resolve().parents[1]
    mp = root / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not mp.is_file():
        return
    ok, msgs = validate_scenarios(
        [{"scenario_id": "x", "manifest_path": str(mp), "agent_explanation": {}}],
        require_hypothesis=True,
    )
    assert ok is False
    assert any("hypothesis" in m for m in msgs)


def test_validate_scenarios_require_hypothesis_accepts_string() -> None:
    root = Path(__file__).resolve().parents[1]
    mp = root / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not mp.is_file():
        return
    ok, msgs = validate_scenarios(
        [
            {
                "scenario_id": "x",
                "manifest_path": str(mp),
                "agent_explanation": {"hypothesis": "Expect non-negative cumulative PnL on this window."},
            }
        ],
        require_hypothesis=True,
    )
    assert ok is True


def test_extract_scenario_echo_includes_tier_fields() -> None:
    d = extract_scenario_echo_fields(
        {
            "manifest_path": "/m",
            "tier": "T1",
            "evaluation_window": {"calendar_months": 12},
            "game_spec_ref": "GAME_SPEC_INDICATOR_PATTERN_V1.md",
        }
    )
    assert d["tier"] == "T1"
    assert d["evaluation_window"]["calendar_months"] == 12
