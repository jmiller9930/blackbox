"""Paired baseline vs candidate outcomes: WIN / NOT_WIN / EXCLUDED."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from modules.anna_training.execution_ledger import compute_pnl_usd

OutcomeClass = Literal["WIN", "NOT_WIN", "EXCLUDED"]


@dataclass(frozen=True)
class PairedTradeSnapshot:
    """Minimal fields for pairing + PnL (deterministic)."""

    market_event_id: str
    lane: str
    strategy_id: str
    mode: str
    side: str | None
    entry_price: float | None
    exit_price: float | None
    size: float | None
    entry_time: str | None
    exit_time: str | None
    symbol: str
    pnl_usd: float | None


def pnl_from_row(row: dict[str, Any]) -> float | None:
    """Economic PnL: recompute from prices when possible (matches ledger)."""
    mode = (row.get("mode") or "").strip().lower()
    if mode not in ("live", "paper"):
        return None
    side = row.get("side")
    ep = row.get("entry_price")
    xp = row.get("exit_price")
    sz = row.get("size")
    if side is None or ep is None or xp is None or sz is None:
        return None
    try:
        return compute_pnl_usd(
            entry_price=float(ep),
            exit_price=float(xp),
            size=float(sz),
            side=str(side),
        )
    except ValueError:
        return None


def classify_paired_outcome(
    *,
    pnl_candidate: float | None,
    pnl_baseline: float | None,
    candidate_passes_risk: bool,
    exclusion_reason: str | None,
) -> tuple[OutcomeClass, str | None]:
    """
    Single observation per market_event_id (caller enforces uniqueness).

    WIN: candidate PnL > baseline PnL AND risk OK.
    NOT_WIN: candidate <= baseline OR risk fail (when evaluable).
    EXCLUDED: cannot evaluate (missing PnL, pairing invalid, etc.).
    """
    if exclusion_reason:
        return "EXCLUDED", exclusion_reason
    if pnl_candidate is None or pnl_baseline is None:
        return "EXCLUDED", "missing_pnl"
    if not candidate_passes_risk:
        return "NOT_WIN", None
    if pnl_candidate > pnl_baseline:
        return "WIN", None
    return "NOT_WIN", None
