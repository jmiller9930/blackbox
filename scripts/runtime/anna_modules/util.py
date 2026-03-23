"""Shared helpers for Anna modules (time, numeric parsing)."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
PROPOSAL_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def try_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def read_float(blob: dict[str, Any], key: str) -> float | None:
    return try_float(blob.get(key))
