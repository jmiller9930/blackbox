"""Grade 12 paper exit gates — curriculum tools first, then numeric cohort (paper_trades.jsonl)."""

from __future__ import annotations

import os
from typing import Any

from modules.anna_training.curriculum_tools import (
    TOOL_IDS,
    curriculum_tools_complete,
    missing_grade_12_tools,
    normalize_tool_mastery,
)
from modules.anna_training.paper_trades import load_paper_trades, summarize_trades
from modules.anna_training.store import load_state


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _env_optional_float(name: str) -> float | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _skip_curriculum_tools_gate() -> bool:
    return (os.environ.get("ANNA_SKIP_CURRICULUM_TOOLS_GATE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def evaluate_grade12_gates(training_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return PASS/FAIL: (1) all Grade 12 curriculum tools passed, (2) numeric paper cohort.

    ``training_state``: optional in-memory state (e.g. during ``save_state`` before disk write).
    When provided, ``grade_12_tool_mastery`` is taken from it; paper trades still come from disk.

    Env (numeric):
      ANNA_GRADE12_MIN_WIN_RATE — default 0.6
      ANNA_GRADE12_MIN_DECISIVE_TRADES — default 30
    Env (numeric, optional capital — evaluated only after curriculum tools PASS):
      ANNA_GRADE12_PAPER_BANKROLL_START_USD — notional starting equity for display / return gate
      ANNA_GRADE12_MIN_NET_PNL_USD — require sum(pnl_usd) on cohort >= this
      ANNA_GRADE12_MIN_EQUITY_USD — require (start + net P&L) >= this (start env required)
      ANNA_GRADE12_MIN_BANKROLL_RETURN_FRAC — e.g. 0.05 requires 5% gain on start (start env required, >0)
    Env (tools bypass, tests/dev only):
      ANNA_SKIP_CURRICULUM_TOOLS_GATE=1 — ignore tool checklist (numeric only)

    Order: tools must be complete before the 60% / min-N slice is considered for overall PASS.
    """
    min_wr = _env_float("ANNA_GRADE12_MIN_WIN_RATE", 0.6)
    min_decisive = _env_int("ANNA_GRADE12_MIN_DECISIVE_TRADES", 30)

    st = training_state if training_state is not None else load_state()
    mastery = normalize_tool_mastery(st.get("grade_12_tool_mastery"))
    tools_ok = curriculum_tools_complete(mastery)
    missing_tools = missing_grade_12_tools(mastery)
    if _skip_curriculum_tools_gate():
        tools_ok = True
        missing_tools = []

    trades = load_paper_trades()
    s = summarize_trades(trades)
    decisive = s.wins + s.losses
    wr = s.win_rate

    numeric_blockers: list[str] = []
    if decisive < min_decisive:
        numeric_blockers.append(f"decisive_trades_below_minimum ({decisive} < {min_decisive})")
    if wr is None or decisive == 0:
        numeric_blockers.append("no_decisive_trades")
    elif wr < min_wr:
        numeric_blockers.append(f"win_rate_below_minimum ({wr:.4f} < {min_wr})")

    total_pnl = float(s.total_pnl_usd)
    bankroll_start = _env_optional_float("ANNA_GRADE12_PAPER_BANKROLL_START_USD")
    min_net_pnl = _env_optional_float("ANNA_GRADE12_MIN_NET_PNL_USD")
    min_equity = _env_optional_float("ANNA_GRADE12_MIN_EQUITY_USD")
    min_return_frac = _env_optional_float("ANNA_GRADE12_MIN_BANKROLL_RETURN_FRAC")
    equity_usd = (bankroll_start + total_pnl) if bankroll_start is not None else None

    if tools_ok:
        if min_net_pnl is not None and total_pnl < min_net_pnl:
            numeric_blockers.append(f"net_pnl_below_minimum ({total_pnl:.2f} < {min_net_pnl:.2f})")
        if min_equity is not None:
            if equity_usd is None:
                numeric_blockers.append(
                    "equity_gate_requires_ANNA_GRADE12_PAPER_BANKROLL_START_USD (set notional start)"
                )
            elif equity_usd < min_equity:
                numeric_blockers.append(f"equity_below_minimum ({equity_usd:.2f} < {min_equity:.2f})")
        if min_return_frac is not None:
            if bankroll_start is None or bankroll_start <= 0:
                numeric_blockers.append(
                    "return_gate_requires_positive_ANNA_GRADE12_PAPER_BANKROLL_START_USD"
                )
            elif equity_usd is not None:
                target_equity = bankroll_start * (1.0 + min_return_frac)
                if equity_usd < target_equity - 1e-9:
                    numeric_blockers.append(
                        "return_on_bankroll_below_minimum "
                        f"(equity {equity_usd:.2f} < target {target_equity:.2f} "
                        f"for {min_return_frac:.4f} frac on start {bankroll_start:.2f})"
                    )

    numeric_ok = len(numeric_blockers) == 0

    tool_blockers: list[str] = []
    current_focus: str | None = None
    if not tools_ok and missing_tools:
        current_focus = missing_tools[0]
        chain = " → ".join(missing_tools)
        tool_blockers.append(
            f"grade_12_current_focus: {current_focus} — complete ONLY this skill next (sequential 1/{len(TOOL_IDS)}). "
            f"Order for remaining work: {chain}. After evidence: `anna tool-pass {current_focus}`. "
            f"`anna tool-list` for titles."
        )

    # One-at-a-time UX: do not flood NOT PASS with numeric failures while tools are incomplete.
    if tools_ok:
        blockers = tool_blockers + numeric_blockers
    else:
        defer = (
            "Paper numeric cohort gate is deferred until all four curriculum tools are passed "
            "(no trade-count / win-rate headline until then)."
        )
        blockers = tool_blockers + ([defer] if tool_blockers else [])

    overall_ok = bool(tools_ok and numeric_ok)

    return {
        "gate_id": "grade12_paper_win_rate_v1",
        "pass": overall_ok,
        "curriculum_tools_pass": tools_ok,
        "numeric_gate_pass": numeric_ok,
        "tool_blockers": tool_blockers,
        "numeric_blockers": numeric_blockers,
        "grade_12_current_focus": current_focus,
        "numeric_gate_deferred_until_tools": not tools_ok,
        "grade_12_tool_mastery": mastery,
        "missing_curriculum_tools": missing_tools,
        "min_win_rate": min_wr,
        "min_decisive_trades": min_decisive,
        "decisive_trades": decisive,
        "wins": s.wins,
        "losses": s.losses,
        "win_rate": wr,
        "total_trades_logged": s.trade_count,
        "total_pnl_usd": total_pnl,
        "paper_bankroll_start_usd": bankroll_start,
        "paper_equity_usd": equity_usd,
        "min_net_pnl_usd": min_net_pnl,
        "min_equity_usd": min_equity,
        "min_bankroll_return_frac": min_return_frac,
        "blockers": blockers,
        "note": "Pass requires curriculum tools in sequence (one focus at a time in the deck), then numeric paper cohort. RCS/RCA human sign-off may still apply per ANNA_GOES_TO_SCHOOL.md.",
    }
