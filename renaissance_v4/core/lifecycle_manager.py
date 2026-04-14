"""
lifecycle_manager.py

Purpose:
Phase 8 — single place to combine scorecard metrics, decay hints, and advisory lifecycle labels.

Usage:
Delegates to performance_metrics.recommend_lifecycle_state and decay_detector flags.

Version:
v1.0

Change History:
- v1.0 Initial Phase 8 scaffold (phase8_to_11 pack).
"""

from __future__ import annotations

from renaissance_v4.core.decay_detector import persistent_drawdown_flag
from renaissance_v4.core.performance_metrics import recommend_lifecycle_state


def advisory_lifecycle_state(
    total_trades: int,
    expectancy: float,
    max_drawdown: float,
) -> str:
    """
    Return an advisory lifecycle label: frozen overrides when decay detector fires.
    """
    if persistent_drawdown_flag(expectancy, max_drawdown, total_trades):
        return "frozen"
    return recommend_lifecycle_state(total_trades, expectancy, max_drawdown)
