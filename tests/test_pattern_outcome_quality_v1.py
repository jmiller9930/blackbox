"""Pattern outcome quality v1 — deterministic metrics from ledger outcomes."""

from __future__ import annotations

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.pattern_outcome_quality_v1 import (
    DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY,
    compute_pattern_outcome_quality_v1,
    diff_outcome_quality_v1,
)


def _o(
    pnl: float,
    mae: float,
    mfe: float,
) -> OutcomeRecord:
    return OutcomeRecord(
        trade_id="t",
        symbol="S",
        direction="long",
        entry_time=1,
        exit_time=2,
        entry_price=1.0,
        exit_price=1.0,
        pnl=pnl,
        mae=mae,
        mfe=mfe,
        exit_reason="test",
    )


def test_outcome_quality_expectancy_and_ratio() -> None:
    outcomes = [_o(100, 50, 150), _o(-40, 80, 10), _o(20, 5, 30)]
    q = compute_pattern_outcome_quality_v1(outcomes)
    assert q["trades_count"] == 3
    assert q["wins_count"] == 2
    assert q["losses_count"] == 1
    assert abs(q["expectancy_per_trade"] - (80.0 / 3.0)) < 1e-5
    assert q["avg_win_size"] == 60.0
    assert q["avg_loss_size"] == 40.0
    assert q["win_loss_size_ratio"] == 1.5


def test_diff_outcome_quality() -> None:
    a = compute_pattern_outcome_quality_v1([_o(10, 1, 20)])
    b = compute_pattern_outcome_quality_v1([_o(20, 1, 20)])
    d = diff_outcome_quality_v1(a, b)
    assert d["expectancy_per_trade_delta"] == 10.0


def test_default_goal_v2_shape() -> None:
    assert DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY["goal_name"] == "pattern_outcome_quality"
    assert DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY["primary_metric"] == "expectancy_per_trade"
