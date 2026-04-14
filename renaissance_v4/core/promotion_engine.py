"""
promotion_engine.py

Purpose:
Phase 8 — adaptive multipliers for signal weights from rolling expectancy and sample size.

Usage:
Call from fusion or a future promotion loop when scorecard metrics are available.

Version:
v1.0

Change History:
- v1.0 Initial Phase 8 scaffold (phase8_to_11 pack).
"""

from __future__ import annotations

MIN_TRADES_FOR_ADJUSTMENT = 20


def adjust_weight(signal_name: str, expectancy: float, trades: int) -> float:
    """
    Return a positive multiplier applied to a signal's base fusion weight.

    Below MIN_TRADES_FOR_ADJUSTMENT trades, the multiplier stays neutral (1.0).
    """
    _ = signal_name
    if trades < MIN_TRADES_FOR_ADJUSTMENT:
        return 1.0
    if expectancy > 0:
        return 1.1
    return 0.7
