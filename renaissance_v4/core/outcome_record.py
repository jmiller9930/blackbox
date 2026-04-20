"""
outcome_record.py

Purpose:
Define the canonical OutcomeRecord object for completed RenaissanceV4 trades.

Usage:
Created when a simulated trade closes and consumed by learning ledger and scorecard logic.

Version:
v1.0

Change History:
- v1.0 Initial Phase 7 implementation.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutcomeRecord:
    """
    Canonical completed-trade record for learning and performance measurement.
    """

    trade_id: str
    symbol: str
    direction: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    pnl: float
    mae: float
    mfe: float
    exit_reason: str
    contributing_signals: list[str] = field(default_factory=list)
    regime: str = "unknown"
    size_tier: str = "zero"
    notional_fraction: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


def outcome_record_to_jsonable(o: OutcomeRecord) -> dict[str, Any]:
    """JSON-serializable dict for worker → parent IPC (parallel batch Directive 09)."""
    d = dataclasses.asdict(o)
    d["__schema__"] = "outcome_record_v1"
    return d


def outcome_record_from_jsonable(d: dict[str, Any]) -> OutcomeRecord:
    """Rebuild :class:`OutcomeRecord` from :func:`outcome_record_to_jsonable` output."""
    d = {k: v for k, v in d.items() if k != "__schema__"}
    fields = {f.name for f in dataclasses.fields(OutcomeRecord)}
    filtered = {k: v for k, v in d.items() if k in fields}
    return OutcomeRecord(**filtered)
