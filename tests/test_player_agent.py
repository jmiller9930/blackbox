"""Player agent orchestrator (narrative + batch wrapper)."""

from __future__ import annotations

from renaissance_v4.game_theory.player_agent import (
    ensure_agent_explanations,
    markdown_operator_report,
    propose_tier1_scenario,
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
