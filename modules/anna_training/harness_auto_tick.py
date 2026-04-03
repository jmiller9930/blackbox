"""Optional automated rows on Karpathy ticks — **lab cohort fuel only** (opt-in, synthetic).

This is **not** “paper trading” in the sense of ANNA_GOES_TO_SCHOOL.md §1.1.1 (same chain as live,
market-grounded, sim settlement). These lines exist so the numeric gate can accumulate **decisive
counts** when enabled; they are tagged ``synthetic: true`` and must not be confused with edge.

Real paper-trading outcomes still come from the **execution / paper adapter path** (e.g. Jack) or
operator ``log-trade`` with governance.

Env (all optional except the master switch):
  ANNA_KARPATHY_AUTO_PAPER_HARNESS — default off; set 1/true/on to enable.
  ANNA_KARPATHY_AUTO_PAPER_EVERY_N — run every N supervisor iterations (default 1).
  ANNA_HARNESS_SYMBOL — default SOL-PERP
  ANNA_HARNESS_TIMEFRAME — default 5m

Rows are deterministic from ``karpathy_iteration`` and tagged ``synthetic: true``,
``source=karpathy_harness_sim``.
"""

from __future__ import annotations

import os
from typing import Any


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def run_automated_paper_harness_tick(
    *,
    karpathy_iteration: int,
    g12: dict[str, Any],
    force: bool = False,
) -> dict[str, Any] | None:
    """
    If enabled (or ``force`` for CLI smoke tests), append one synthetic paper row when
    curriculum tools pass and overall gate is not yet satisfied.

    Returns a small status dict when a row was written, else None.
    """
    if not force and not _env_bool("ANNA_KARPATHY_AUTO_PAPER_HARNESS"):
        return None
    if not bool(g12.get("curriculum_tools_pass")):
        return None
    if bool(g12.get("pass")):
        return None
    every_n = _env_int("ANNA_KARPATHY_AUTO_PAPER_EVERY_N", 1)
    if karpathy_iteration % every_n != 0:
        return None

    from modules.anna_training.paper_trades import append_paper_trade

    sym = (os.environ.get("ANNA_HARNESS_SYMBOL") or "SOL-PERP").strip() or "SOL-PERP"
    tf = (os.environ.get("ANNA_HARNESS_TIMEFRAME") or "5m").strip() or "5m"
    h = (int(karpathy_iteration) * 7919 + 12345) & 0xFFFFFFFF
    won = (h % 2) == 0
    result = "won" if won else "lost"
    raw_pnl = ((h % 401) - 200) / 25.0
    pnl = abs(raw_pnl) if won else -abs(raw_pnl)
    side = "long" if ((h // 7) % 2) == 0 else "short"

    row = append_paper_trade(
        symbol=sym,
        side=side,
        result=result,
        pnl_usd=float(pnl),
        timeframe=tf,
        venue="jupiter_perp",
        notes=(
            "Synthetic cohort tick (lab). Deterministic from karpathy_loop_iteration; "
            "not a live fill. Disable with ANNA_KARPATHY_AUTO_PAPER_HARNESS=0."
        ),
        source="karpathy_harness_sim",
        strategy_label="karpathy_auto_cohort_v1",
        synthetic=True,
        log_manual_activity=True,
        activity_phase="harness_auto",
    )
    return {
        "ok": True,
        "synthetic": True,
        "trade_id": row.get("trade_id"),
        "karpathy_iteration": karpathy_iteration,
    }
