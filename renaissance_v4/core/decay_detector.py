"""
decay_detector.py

Purpose:
Phase 8 — detect persistent underperformance or stress that should freeze or reduce a signal.

**BASELINE / GOVERNANCE:** Do not auto-enforce until `RenaissanceV4_baseline_v1` is accepted.

Usage:
Feed scorecard-style metrics; use output to gate weighting or lifecycle transitions.

Version:
v1.0

Change History:
- v1.0 Initial Phase 8 scaffold (phase8_to_11 pack).
"""

from __future__ import annotations

FREEZE_DRAWDOWN_MULTIPLIER = 25.0
MIN_TRADES = 20


def persistent_drawdown_flag(expectancy: float, max_drawdown: float, trades: int) -> bool:
    """
    Heuristic freeze hook: severe drawdown relative to |expectancy| once sample is non-trivial.
    Aligns with recommend_lifecycle_state frozen branch in performance_metrics.
    """
    if trades < MIN_TRADES:
        return False
    return max_drawdown > abs(expectancy) * FREEZE_DRAWDOWN_MULTIPLIER


def negative_expectancy_flag(expectancy: float, trades: int) -> bool:
    """True when expectancy is negative and the sample is large enough to matter."""
    return trades >= MIN_TRADES and expectancy < 0.0
