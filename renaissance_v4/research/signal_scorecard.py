"""
signal_scorecard.py

Purpose:
Build per-signal-family scorecards from completed RenaissanceV4 outcomes.

Usage:
Used after replay to summarize which signal families performed well or poorly.

Version:
v1.0

Change History:
- v1.0 Initial Phase 7 implementation.
"""

from __future__ import annotations

from collections import defaultdict

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.performance_metrics import compute_summary_metrics, recommend_lifecycle_state


def build_signal_scorecards(outcomes: list[OutcomeRecord]) -> dict[str, dict]:
    """
    Group outcomes by contributing signal name and return a scorecard per signal.
    """
    grouped: dict[str, list[OutcomeRecord]] = defaultdict(list)

    for outcome in outcomes:
        for signal_name in outcome.contributing_signals:
            grouped[signal_name].append(outcome)

    scorecards: dict[str, dict] = {}

    for signal_name, signal_outcomes in grouped.items():
        metrics = compute_summary_metrics(signal_outcomes)
        lifecycle_state = recommend_lifecycle_state(
            total_trades=metrics["total_trades"],
            expectancy=metrics["expectancy"],
            max_drawdown=metrics["max_drawdown"],
        )
        scorecards[signal_name] = {
            **metrics,
            "lifecycle_state": lifecycle_state,
        }
        print(f"[signal_scorecard] signal={signal_name} scorecard={scorecards[signal_name]}")

    return scorecards
