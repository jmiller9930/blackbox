"""
risk_decision.py

Purpose:
Define the canonical RiskDecision object for RenaissanceV4 risk governance.

Usage:
Produced by the risk governor and consumed by replay, execution gating, and later trade logic.

Version:
v1.0

Change History:
- v1.0 Initial Phase 5 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskDecision:
    """
    Canonical output object for RenaissanceV4 risk governance.
    """

    allowed: bool
    size_tier: str
    notional_fraction: float
    compression_factor: float
    veto_reasons: list[str] = field(default_factory=list)
    debug_trace: dict[str, Any] = field(default_factory=dict)
