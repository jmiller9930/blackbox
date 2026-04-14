"""
fusion_result.py

Purpose:
Define the canonical FusionResult object for RenaissanceV4 evidence fusion.

Usage:
Produced by the fusion engine and consumed by replay, risk, and later execution logic.

Version:
v1.0

Change History:
- v1.0 Initial Phase 4 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FusionResult:
    """
    Canonical output object for evidence fusion across signal modules.
    """

    direction: str
    fusion_score: float
    long_score: float
    short_score: float
    gross_score: float
    conflict_score: float
    overlap_penalty: float
    threshold_passed: bool
    contributing_signals: list[str] = field(default_factory=list)
    suppressed_signals: list[str] = field(default_factory=list)
    debug_trace: dict[str, Any] = field(default_factory=dict)
