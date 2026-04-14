"""
signal_result.py

Purpose:
Define the canonical SignalResult object for RenaissanceV4 signal modules.

Usage:
Returned by all signal classes and consumed by replay, fusion, and later risk logic.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SignalResult:
    """
    Canonical result object returned by each signal module.
    """

    signal_name: str
    direction: str
    confidence: float
    expected_edge: float
    regime_fit: float
    stability_score: float
    active: bool
    suppression_reason: str
    evidence_trace: dict[str, Any] = field(default_factory=dict)
