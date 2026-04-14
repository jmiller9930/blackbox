"""
trade_state.py

Purpose:
Hold open simulated position state for Phase 6 execution manager.

Version:
v1.1

Change History:
- v1.0 Initial Phase 6 implementation.
- v1.1 Phase 7: entry time, risk tier, contributing signals, excursion bounds for MAE/MFE.
- v1.2 DV-ARCH-CORRECTION-013: entry_regime snapshot for outcome diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradeState:
    symbol: str
    entry_price: float
    direction: str
    stop_loss: float
    take_profit: float
    size: float
    entry_time: int = 0
    contributing_signal_names: list[str] = field(default_factory=list)
    risk_size_tier: str = "zero"
    risk_notional_fraction: float = 0.0
    entry_regime: str = "unknown"
    min_low_seen: float | None = None
    max_high_seen: float | None = None
    open: bool = True
