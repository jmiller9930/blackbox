"""Deterministic hypothesis hash for distinctiveness (no fuzzy clustering in v1)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def normalized_hypothesis_hash(hypothesis: dict[str, Any]) -> str:
    """
    Canonical SHA-256 over JSON with sorted keys — stable across key order.
    Use for duplicate detection vs other active tests.
    """
    body = json.dumps(hypothesis, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
