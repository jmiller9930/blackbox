"""
determinism.py

Purpose:
Deterministic identifiers and validation checksums for repeatable replay proofs.

Version:
v1.0

Change History:
- v1.0 Baseline v1 acceptance (architect).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def deterministic_trade_id(
    symbol: str,
    entry_time: int,
    exit_time: int,
    entry_price: float,
    exit_price: float,
    direction: str,
) -> str:
    """Stable trade id from prices and times (no random UUIDs)."""
    payload = f"{symbol}|{entry_time}|{exit_time}|{entry_price:.10f}|{exit_price:.10f}|{direction}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def deterministic_decision_id(bar_timestamp: int, bar_index: int) -> str:
    """Stable decision id for a replay step."""
    payload = f"{bar_timestamp}|{bar_index}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def validation_checksum(summary: dict[str, Any], cumulative_pnl: float, total_outcomes: int) -> str:
    """
    Single-line hash for two-run equality checks (same DB + same code -> same checksum).
    """
    payload = json.dumps(
        {
            "summary": summary,
            "cumulative_pnl": cumulative_pnl,
            "total_outcomes": total_outcomes,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
