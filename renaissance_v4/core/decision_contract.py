"""
decision_contract.py

Purpose:
Define the canonical RenaissanceV4 decision contract.

Usage:
Used by replay and live evaluation to ensure a single output structure.

Version:
v1.0

Change History:
- v1.0 Initial implementation scaffold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DecisionContract:
    """
    Canonical decision object for one evaluation cycle.
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
    contributing_signals: list[str] = field(default_factory=list)
    suppressed_signals: list[str] = field(default_factory=list)
    risk_veto_reasons: list[str] = field(default_factory=list)
