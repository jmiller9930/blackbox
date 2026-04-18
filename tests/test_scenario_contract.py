"""Scenario batch JSON validation helpers."""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.game_theory.scenario_contract import extract_agent_fields, validate_scenarios


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
