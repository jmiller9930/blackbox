"""
Notification priority tiers (SMS and templates).

Tier 1 — Trading / execution (money at risk; worst outcomes emphasized).
Tier 2 — System / availability (cannot operate safely or core dependency down).
Tier 3 — General / agents (milestones, progress, non-blocking info).

Env:
  BLACKBOX_NOTIFY_SMS_TIERS — comma-separated subset of 1,2,3 (default: all three).
    Example: 1,2  → SMS only for tiers 1–2; tier-3 events return sms_tier_filtered.

  BLACKBOX_NOTIFY_TRADE_ROUTINE_TIER — set to 3, true, yes, or on: routine-looking trade
    statuses (filled, submitted, …) use tier 3 if they do not match loss/fail patterns; else tier 1.
"""

from __future__ import annotations

import os
import re
from enum import IntEnum


class NotificationTier(IntEnum):
    TRADE = 1
    SYSTEM = 2
    GENERAL = 3


def parse_sms_allowed_tiers() -> set[int]:
    """Default: {1, 2, 3}. Invalid tokens ignored."""
    raw = (os.environ.get("BLACKBOX_NOTIFY_SMS_TIERS") or "1,2,3").strip()
    if not raw:
        return {1, 2, 3}
    out: set[int] = set()
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        try:
            n = int(p)
            if n in (1, 2, 3):
                out.add(n)
        except ValueError:
            continue
    return out if out else {1, 2, 3}


def tier_allowed_sms(tier: int) -> bool:
    return int(tier) in parse_sms_allowed_tiers()


_BAD_TRADE = re.compile(
    r"loss|fail|reject|error|cancel|liquidat|margin|slippage|breach|kill|halt",
    re.IGNORECASE,
)


def resolve_trade_tier(
    *,
    status: str,
    tier_override: int | None,
) -> int:
    """
    Default: tier 1 (all trades treated as high priority).

    If BLACKBOX_NOTIFY_TRADE_ROUTINE_TIER is 3 and status looks routine (no bad keywords),
    return tier 3; otherwise tier 1.
    """
    if tier_override is not None:
        return int(tier_override)

    want_routine = (os.environ.get("BLACKBOX_NOTIFY_TRADE_ROUTINE_TIER") or "").strip().lower() in (
        "3",
        "true",
        "yes",
        "on",
    )
    if not want_routine:
        return NotificationTier.TRADE

    st = status or ""
    if _BAD_TRADE.search(st):
        return NotificationTier.TRADE

    st_l = st.lower()
    routine_markers = ("fill", "filled", "submit", "ack", "pending", "partial", "open", "route")
    if any(m in st_l for m in routine_markers):
        return NotificationTier.GENERAL

    return NotificationTier.TRADE


__all__ = [
    "NotificationTier",
    "parse_sms_allowed_tiers",
    "tier_allowed_sms",
    "resolve_trade_tier",
]
