"""
Canonical row-level label definitions for Phase 1 (baseline Jupiter_2 lifecycle trades).

These definitions are tied to **ledger truth**: ``exit_reason`` and ``pnl_usd`` from
``execution_trades`` for rows with lifecycle exits only (``STOP_LOSS`` / ``TAKE_PROFIT``).

**beats_baseline (Phase 1):** For rows that **are** the baseline trade, there is no second
baseline to beat. Phase 1 defines ``beats_baseline`` as **positive economic outcome vs flat**
(``pnl_usd > 0``). When Anna lane comparisons exist, a future schema version may add
``beats_baseline_vs_anna`` or redefine using paired ``market_event_id`` deltas — not Phase 1.
"""

from __future__ import annotations

from typing import Any

# How many **subsequent** closed 5m bars (after the exit bar) to scan for whipsaw geometry.
WHIPSAW_LOOKAHEAD_BARS = 5


def trade_success_label(*, exit_reason: str | None) -> bool:
    """
    True iff the lifecycle exit was **take profit** (authoritative rulebook).

    Deterministic: ``str(exit_reason).strip().upper() == 'TAKE_PROFIT'``.
    """
    return str(exit_reason or "").strip().upper() == "TAKE_PROFIT"


def stopped_early_label(*, exit_reason: str | None) -> bool:
    """
    True iff the lifecycle exit was **stop loss** (stopped out per policy).

    Deterministic: ``str(exit_reason).strip().upper() == 'STOP_LOSS'``.
    """
    return str(exit_reason or "").strip().upper() == "STOP_LOSS"


def beats_baseline_label(*, pnl_usd: float | None) -> bool:
    """
    Phase 1: True iff **pnl_usd > 0** (outperforms **flat** / zero PnL on the same trade).

    Not a comparison to a second baseline series (N/A for pure baseline rows).
    """
    if pnl_usd is None:
        return False
    try:
        return float(pnl_usd) > 1e-12
    except (TypeError, ValueError):
        return False


def compute_whipsaw_flag(
    *,
    side: str | None,
    entry_price: float | None,
    exit_reason: str | None,
    bars_after_exit: list[dict[str, Any]],
) -> bool:
    """
    **Whipsaw (Phase 1, geometric):** stopped by **STOP_LOSS**, then price **revisits**
    the **entry** level within the next ``WHIPSAW_LOOKAHEAD_BARS`` closed bars (exclusive
    of the exit bar itself; ``bars_after_exit`` are those bars, ascending time).

    - **long:** ``max(high) >= entry_price`` over those bars.
    - **short:** ``min(low) <= entry_price`` over those bars.

    If ``stopped_early`` is False, returns False. If ``entry_price`` is missing or
    ``bars_after_exit`` empty, returns False.
    """
    if not stopped_early_label(exit_reason=exit_reason):
        return False
    if entry_price is None:
        return False
    try:
        ep = float(entry_price)
    except (TypeError, ValueError):
        return False
    if not bars_after_exit:
        return False
    sd = str(side or "").strip().lower()
    highs: list[float] = []
    lows: list[float] = []
    for b in bars_after_exit:
        try:
            highs.append(float(b["high"]))
            lows.append(float(b["low"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not highs:
        return False
    if sd == "long":
        return max(highs) >= ep
    if sd == "short":
        return min(lows) <= ep
    return False
