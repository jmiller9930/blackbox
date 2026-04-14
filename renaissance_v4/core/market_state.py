"""
market_state.py

Purpose:
Define the canonical MarketState object for one replay step.

Usage:
Produced by the market state builder and consumed by the feature engine.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketState:
    """
    Represents the currently known historical market window at one replay step.
    """

    symbol: str
    timestamp: int
    closes: list[float]
    highs: list[float]
    lows: list[float]
    opens: list[float]
    volumes: list[float]
    current_open: float
    current_high: float
    current_low: float
    current_close: float
    current_volume: float
