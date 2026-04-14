"""
portfolio_manager.py

Purpose:
Phase 10 — coarse portfolio-level exposure gate before new risk is taken.

Usage:
Optional second check after risk governor when multiple positions or books exist.

Version:
v1.0

Change History:
- v1.0 Initial Phase 10 scaffold (phase8_to_11 pack).
"""

from __future__ import annotations


class PortfolioManager:
    def __init__(self, max_exposure: float = 0.05) -> None:
        self.max_exposure = max_exposure

    def allow_trade(self, current_exposure: float) -> bool:
        """
        Return True if adding a trade is allowed under the exposure ceiling.
        """
        return current_exposure < self.max_exposure
