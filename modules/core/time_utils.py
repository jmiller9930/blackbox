"""Timezone-aware clock helpers for shared modules."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)
