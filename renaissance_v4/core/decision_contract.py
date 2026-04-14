"""
decision_contract.py

Purpose:
Define the canonical Phase 1 decision contract for RenaissanceV4.

Usage:
Used by replay and later live evaluation code to keep one consistent output structure.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DecisionContract:
    """
    Canonical decision object for one evaluation cycle.
    This starts simple in Phase 1 and will expand in later phases.
    """

    decision_id: str
    symbol: str
    timestamp: int
    market_regime: str
    direction: str
    fusion_score: float
    confidence_score: float
    edge_score: float
    risk_budget: float
    execution_allowed: bool
    reason_trace: dict[str, Any] = field(default_factory=dict)
