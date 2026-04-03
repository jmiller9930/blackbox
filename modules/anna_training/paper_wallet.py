"""Fictitious paper wallet — notional start, goal, and horizon (not live capital)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

# Contract: training narrative only; gates use starting_usd for equity = start + sum(pnl).
DEFAULT_PAPER_WALLET: dict[str, Any] = {
    "schema": "paper_wallet_v1",
    "starting_usd": 100.0,
    # Static fallback when ANNA_PAPER_GOAL_ADAPTIVE=0. With adaptive on (default), target slides 5–15%/week from market data.
    "goal_target_equity_usd": 110.0,
    "goal_return_frac": 0.10,
    "goal_horizon_days": 7,
    "currency": "USD",
    "clock_start_utc": None,
    "note": (
        "Fictitious paper only — not live capital. Default ANNA_PAPER_GOAL_ADAPTIVE=1 slides weekly "
        "goal between 5% and 15% from recent SOL-USD ticks (range/vol + gate health); set ANNA_PAPER_GOAL_ADAPTIVE=0 "
        "to use goal_return_frac from this object only."
    ),
}


def merge_paper_wallet_into_state(st: dict[str, Any]) -> None:
    """Fill missing paper_wallet keys from defaults (in-place)."""
    pw = st.get("paper_wallet")
    if not isinstance(pw, dict):
        st["paper_wallet"] = {**DEFAULT_PAPER_WALLET}
        return
    for k, v in DEFAULT_PAPER_WALLET.items():
        if k not in pw:
            pw[k] = v


def resolve_paper_bankroll_start_usd(training_state: dict[str, Any]) -> float:
    """Starting notional for P&L + equity. Env overrides state; default $100 from wallet."""
    raw = (os.environ.get("ANNA_GRADE12_PAPER_BANKROLL_START_USD") or "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    merge_paper_wallet_into_state(training_state)
    pw = training_state.get("paper_wallet") or {}
    try:
        return float(pw.get("starting_usd", DEFAULT_PAPER_WALLET["starting_usd"]))
    except (TypeError, ValueError):
        return float(DEFAULT_PAPER_WALLET["starting_usd"])


def _parse_utc(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def days_since_clock(clock_start_utc: str | None) -> int | None:
    """Whole days since clock start, UTC; None if clock unset."""
    start = _parse_utc(clock_start_utc)
    if start is None:
        return None
    now = datetime.now(timezone.utc)
    delta = now - start.astimezone(timezone.utc)
    return max(0, int(delta.total_seconds() // 86400))


def ensure_paper_wallet_clock(st: dict[str, Any]) -> bool:
    """Set clock_start_utc once when missing. Returns True if state was mutated."""
    merge_paper_wallet_into_state(st)
    pw = st["paper_wallet"]
    if pw.get("clock_start_utc"):
        return False
    from modules.anna_training.store import utc_now_iso

    pw["clock_start_utc"] = utc_now_iso()
    return True


def goal_progress_lines(
    *,
    training_state: dict[str, Any],
    total_pnl_usd: float,
    bankroll_start: float,
    equity_usd: float | None,
) -> list[str]:
    """Human-readable goal lines for FACT / report card."""
    merge_paper_wallet_into_state(training_state)
    pw = training_state.get("paper_wallet") or {}
    target = float(pw.get("goal_target_equity_usd", DEFAULT_PAPER_WALLET["goal_target_equity_usd"]))
    horizon = int(pw.get("goal_horizon_days", DEFAULT_PAPER_WALLET["goal_horizon_days"]))
    ret = float(pw.get("goal_return_frac", DEFAULT_PAPER_WALLET["goal_return_frac"]))
    days = days_since_clock(pw.get("clock_start_utc"))
    day_part = f"day {days + 1} of {horizon}" if days is not None else "clock starts at first `anna status` / `anna gates` after upgrade"
    eq = equity_usd if equity_usd is not None else (bankroll_start + total_pnl_usd)
    met = eq >= target - 1e-9
    status = "goal equity reached (fictitious)" if met else "working toward goal"
    return [
        f"Paper wallet (fictitious): start ${bankroll_start:,.2f} → current equity ${eq:,.2f} "
        f"→ target ${target:,.2f} (+{ret:.0%} on start) within {horizon} days ({day_part}) — {status}.",
    ]
