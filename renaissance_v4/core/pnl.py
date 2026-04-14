"""
pnl.py

Purpose:
Deterministic paper PnL from entry, exit, notional size, and direction.

Version:
v1.0

Change History:
- v1.0 Initial Phase 6 implementation.
"""

from __future__ import annotations


def compute_pnl(entry: float, exit_: float, size: float, direction: str) -> float:
    if direction == "long":
        return (exit_ - entry) * size
    return (entry - exit_) * size
