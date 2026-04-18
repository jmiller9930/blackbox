"""Pluggable PatternGameAgent facade."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import renaissance_v4.game_theory.pattern_game_agent as pga_mod
from renaissance_v4.game_theory.pattern_game_agent import PatternGameAgent

_REPO = Path(__file__).resolve().parents[1]


def test_plugin_info() -> None:
    a = PatternGameAgent(repo_root=_REPO)
    info = a.plugin_info()
    assert info["kind"] == "pattern_game_player_agent"
    assert str(_REPO) in info["repo_root"]


def test_list_presets_includes_tier1() -> None:
    a = PatternGameAgent(repo_root=_REPO)
    ids = {p["id"] for p in a.list_presets()}
    assert "tier1_twelve_month.example.json" in ids


def test_load_preset() -> None:
    a = PatternGameAgent(repo_root=_REPO)
    rows = a.load_preset("tier1_twelve_month.example.json")
    assert isinstance(rows, list) and len(rows) >= 1
    assert rows[0].get("manifest_path")


def test_load_scenarios_json_wrapped() -> None:
    a = PatternGameAgent(repo_root=_REPO)
    raw = json.dumps({"scenarios": [{"manifest_path": "/x.json", "scenario_id": "s"}]})
    rows = a.load_scenarios_json(raw)
    assert len(rows) == 1


def test_run_preset_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    a = PatternGameAgent(repo_root=_REPO)

    def fake_batch(*args: object, **kwargs: object) -> dict:
        return {"results": [], "report_markdown": "# ok", "anna_narrative": None, "anna_error": None}

    monkeypatch.setattr(pga_mod, "run_player_batch", fake_batch)
    out = a.run_preset("tier1_twelve_month.example.json", with_anna=False)
    assert out["report_markdown"] == "# ok"


def test_run_referee_only_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    a = PatternGameAgent(repo_root=_REPO)

    def fake_parallel(*a: object, **k: object) -> list:
        return [{"ok": True, "scenario_id": "x"}]

    monkeypatch.setattr(pga_mod, "run_scenarios_parallel", fake_parallel)
    scenarios = a.load_preset("tier1_twelve_month.example.json")
    res = a.run_referee_only(scenarios, max_workers=1)
    assert res[0]["scenario_id"] == "x"
