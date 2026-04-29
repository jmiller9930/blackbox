"""GT056 — opportunity selection metrics."""

from __future__ import annotations

from renaissance_v4.game_theory.opportunity_selection_metrics_v1 import (
    compute_opportunity_selection_metrics_v1,
)


def _rec(pnl: float, action: str) -> dict:
    return {
        "student_output": {"student_action_v1": action},
        "referee_outcome_subset": {"pnl": pnl},
    }


def test_compute_opportunity_selection_metrics_basic() -> None:
    recs = [
        _rec(10.0, "enter_long"),
        _rec(-5.0, "enter_short"),
        _rec(3.0, "no_trade"),
        _rec(-8.0, "no_trade"),
    ]
    m = compute_opportunity_selection_metrics_v1(recs)
    assert m["total_possible_setups"] == 4
    assert m["trades_taken"] == 2
    assert m["trades_skipped"] == 2
    assert m["bad_trades_avoided"] == 1
    assert m["good_trades_missed"] == 1
    assert m["wins_taken"] == 1
    assert m["losses_taken"] == 1
    assert m["taken_win_rate"] == 0.5
    assert m["opportunity_win_rate"] == 0.5


def test_skipped_avoided_and_missed_match() -> None:
    recs = [_rec(-1.0, "no_trade"), _rec(2.0, "no_trade")]
    m = compute_opportunity_selection_metrics_v1(recs)
    assert m["bad_trades_avoided"] == m["losses_skipped"] == 1
    assert m["good_trades_missed"] == m["wins_skipped"] == 1
