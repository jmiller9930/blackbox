"""Player agent orchestrator (narrative + batch wrapper)."""

from __future__ import annotations

import renaissance_v4.game_theory.player_agent as player_agent_mod
from renaissance_v4.game_theory.player_agent import (
    ensure_agent_explanations,
    markdown_operator_report,
    propose_tier1_scenario,
    run_player_batch,
)


def test_propose_tier1_has_tier_and_window() -> None:
    s = propose_tier1_scenario("renaissance_v4/configs/manifests/baseline_v1_recipe.json")
    assert s["tier"] == "T1"
    assert s["evaluation_window"]["calendar_months"] == 12
    assert "agent_explanation" in s


def test_ensure_agent_explanations_fills_missing() -> None:
    rows = ensure_agent_explanations([{"scenario_id": "x", "manifest_path": "/m"}])
    assert "why_this_strategy" in rows[0]["agent_explanation"]


def test_markdown_report_renders() -> None:
    md = markdown_operator_report(
        [
            {
                "ok": True,
                "scenario_id": "a",
                "manifest_path": "/x.json",
                "summary": {"wins": 1, "losses": 2, "trades": 3, "win_rate": 0.33, "cumulative_pnl": 0.0},
            }
        ]
    )
    assert "Player agent batch report" in md
    assert "a" in md
    assert "wins=1" in md


def _fake_parallel_result() -> list[dict]:
    return [
        {
            "ok": True,
            "scenario_id": "s1",
            "manifest_path": "m.json",
            "summary": {
                "wins": 1,
                "losses": 0,
                "trades": 1,
                "win_rate": 1.0,
                "cumulative_pnl": 0.0,
            },
        }
    ]


def test_run_player_batch_with_anna_appends_narrative(monkeypatch) -> None:
    monkeypatch.setattr(
        player_agent_mod,
        "run_scenarios_parallel",
        lambda *a, **k: _fake_parallel_result(),
    )
    monkeypatch.setattr(
        player_agent_mod,
        "anna_narrate_pattern_report",
        lambda md, **kw: ("Test narrative only.", None),
    )
    out = run_player_batch([{"manifest_path": "x.json"}], with_anna=True)
    assert out["anna_narrative"] == "Test narrative only."
    assert "Anna — operator narrative" in out["report_markdown"]
    assert "Test narrative only." in out["report_markdown"]


def test_run_player_batch_no_anna_skips_llm(monkeypatch) -> None:
    called: list[int] = []

    def boom(*a, **k):
        called.append(1)
        return ("should not run", None)

    monkeypatch.setattr(
        player_agent_mod,
        "run_scenarios_parallel",
        lambda *a, **k: _fake_parallel_result(),
    )
    monkeypatch.setattr(player_agent_mod, "anna_narrate_pattern_report", boom)
    out = run_player_batch([{"manifest_path": "x.json"}], with_anna=False)
    assert not called
    assert out["anna_narrative"] is None
    assert "Anna — operator narrative" not in out["report_markdown"]
