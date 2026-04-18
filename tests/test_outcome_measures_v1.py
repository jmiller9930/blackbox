"""Tests for outcome_measures_v1 — multi-dimensional interpretation of Referee summary rows."""

from __future__ import annotations

from renaissance_v4.game_theory.run_memory import build_outcome_measures_v1, build_run_memory_record
from renaissance_v4.game_theory.run_session_log import render_human_readable_markdown


def test_outcome_measures_empty_referee() -> None:
    o = build_outcome_measures_v1(None)
    assert o["schema"] == "outcome_measures_v1"
    assert o["from_referee_row"] is False
    assert o["positive_any"] is False
    assert o["positive_signals"] == []


def test_outcome_measures_positive_pnl_and_expectancy() -> None:
    ref = {
        "wins": 3,
        "losses": 2,
        "trades": 5,
        "win_rate": 0.6,
        "cumulative_pnl": 42.5,
        "expectancy": 1.2,
        "average_pnl": 8.5,
        "max_drawdown": 0.0,
    }
    o = build_outcome_measures_v1(ref)
    assert o["from_referee_row"] is True
    assert o["lenses"]["money"] == "positive"
    assert o["lenses"]["edge"] == "positive"
    assert o["lenses"]["win_rate_vs_coinflip"] == "above"
    assert o["positive_any"] is True
    assert "cumulative_pnl_positive" in o["positive_signals"]
    assert "expectancy_positive" in o["positive_signals"]


def test_outcome_measures_all_negative() -> None:
    ref = {
        "wins": 1,
        "losses": 9,
        "trades": 10,
        "win_rate": 0.1,
        "cumulative_pnl": -100.0,
        "expectancy": -5.0,
        "average_pnl": -10.0,
        "max_drawdown": -50.0,
    }
    o = build_outcome_measures_v1(ref)
    assert o["lenses"]["money"] == "negative"
    assert o["lenses"]["edge"] == "non_positive"
    assert o["lenses"]["win_rate_vs_coinflip"] == "at_or_below"
    assert o["lenses"]["drawdown"] == "experienced_drawdown"
    assert o["positive_any"] is False


def test_run_memory_record_includes_outcome_measures() -> None:
    ref = {"cumulative_pnl": 1.0, "expectancy": 0.5, "win_rate": 0.4, "trades": 10}
    rec = build_run_memory_record(
        source="test",
        manifest_path="/tmp/nonexistent_manifest_x.json",
        json_summary_row=ref,
    )
    assert "outcome_measures" in rec
    assert rec["outcome_measures"]["schema"] == "outcome_measures_v1"


def test_human_readable_contains_outcome_section() -> None:
    ref = {"cumulative_pnl": 10.0, "expectancy": 2.0}
    rec = build_run_memory_record(
        source="test",
        manifest_path="/tmp/nonexistent_manifest_y.json",
        json_summary_row=ref,
    )
    md = render_human_readable_markdown(rec)
    assert "Outcome lenses" in md
    assert "same Referee row" in md
