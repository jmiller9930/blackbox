"""
signal_weights.py

Purpose:
Provide stable default signal weights for RenaissanceV4 Phase 4 fusion.

Usage:
Imported by the fusion engine to weight active signals consistently.

Version:
v1.0

Change History:
- v1.0 Initial Phase 4 implementation.
"""

from __future__ import annotations

DEFAULT_SIGNAL_WEIGHTS = {
    "trend_continuation": 1.00,
    "pullback_continuation": 0.90,
    "breakout_expansion": 0.95,
    "mean_reversion_fade": 0.85,
}


def get_signal_weight(signal_name: str) -> float:
    """
    Return the configured default weight for a signal.
    Falls back to 1.0 if the signal name is unknown.
    """
    return DEFAULT_SIGNAL_WEIGHTS.get(signal_name, 1.0)
