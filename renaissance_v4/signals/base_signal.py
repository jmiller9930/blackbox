"""
base_signal.py

Purpose:
Define the abstract base signal contract for all RenaissanceV4 signal modules.

Usage:
Inherited by all signal implementations to guarantee a common interface.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.signals.signal_result import SignalResult


class BaseSignal(ABC):
    """
    Abstract signal interface for all RenaissanceV4 signal modules.
    """

    signal_name: str = "base_signal"

    def configure_from_manifest(self, manifest: dict[str, Any]) -> None:
        """
        Optional manifest-driven thresholds / toggles (memory bundle may merge keys here).
        Default: no-op. Implementations read only whitelisted manifest keys they own.
        """
        return

    @abstractmethod
    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        """
        Evaluate the current market state and return a deterministic SignalResult.
        """
        raise NotImplementedError
