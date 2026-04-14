"""
trade_state.py

Purpose:
Hold open simulated position state for Phase 6 execution manager.

Version:
v1.0

Change History:
- v1.0 Initial Phase 6 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TradeState:
    symbol: str
    entry_price: float
    direction: str
    stop_loss: float
    take_profit: float
    size: float
    open: bool = True
