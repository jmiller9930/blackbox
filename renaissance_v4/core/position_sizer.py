"""
position_sizer.py

Purpose:
Provide stable size-tier to notional-fraction mapping for RenaissanceV4.

Usage:
Imported by the risk governor to convert tier decisions into normalized allocation fractions.

Version:
v1.0

Change History:
- v1.0 Initial Phase 5 implementation.
"""

from __future__ import annotations

SIZE_TIER_TO_NOTIONAL = {
    "zero": 0.00,
    "probe": 0.10,
    "reduced": 0.50,
    "full": 1.00,
}


def size_tier_to_fraction(size_tier: str) -> float:
    """
    Convert a size tier string into a notional fraction.
    Falls back to zero if an unknown tier is provided.
    """
    return SIZE_TIER_TO_NOTIONAL.get(size_tier, 0.0)
