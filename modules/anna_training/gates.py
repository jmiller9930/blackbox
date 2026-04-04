"""Grade 12 paper exit gates — curriculum tools first, then numeric cohort (paper_trades.jsonl).

Paper trades are the **judgment ledger** for training: see :mod:`modules.anna_training.paper_judgment`.
"""

from __future__ import annotations

import os
from typing import Any

from modules.anna_training.paper_judgment import PAPER_LEDGER_AUTHORITATIVE_FOR_TRAINING
from modules.anna_training.curriculum_tools import (
    TOOL_IDS,
    curriculum_tools_complete,
    missing_grade_12_tools,
    normalize_tool_mastery,
)
from modules.anna_training.adaptive_paper_goal import compute_adaptive_paper_goal
from modules.anna_training.paper_trades import (
    cohort_is_vacuous_all_wins_zero_pnl,
    load_paper_trades_for_gates,
    summarize_trades,
)
from modules.anna_training.paper_wallet import (
    DEFAULT_PAPER_WALLET,
    days_since_clock,
    ensure_paper_wallet_clock,
    merge_paper_wallet_into_state,
    resolve_paper_bankroll_start_usd,
)
from modules.anna_training.store import load_state, save_state


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


def _ignore_vacuous_win_streak_gate() -> bool:
    """Allow numeric PASS when every row is won+$0 (dev/tests only — not honest for production)."""
    return (os.environ.get("ANNA_GRADE12_IGNORE_VACUOUS_WIN_STREAK") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def evaluate_grade12_gates(training_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return PASS/FAIL: (1) all Grade 12 curriculum tools passed, (2) numeric paper cohort.

    Cohort metrics read **paper_trades.jsonl** — that log is **authoritative for training judgment**
    (no live settlement; still what Anna is graded on). See ``paper_judgment`` in the return dict.

    ``training_state``: optional in-memory state (e.g. during ``save_state`` before disk write).
    When provided, ``grade_12_tool_mastery`` is taken from it; paper trades still come from disk.

    Env (numeric):
      ANNA_GRADE12_MIN_WIN_RATE — default 0.6
      ANNA_GRADE12_MIN_DECISIVE_TRADES — default 30
    Env (numeric, optional capital — overrides state wallet start — evaluated only after curriculum tools PASS):
      ANNA_GRADE12_PAPER_BANKROLL_START_USD — paper starting equity for gate math (default from state paper_wallet: $100)
    Weekly paper goal (informational paper_goal_met; still counts for “did she hit the bar” reporting):
      ANNA_PAPER_GOAL_ADAPTIVE — default 1: slide goal return 5%–15% from recent market_ticks (+ gate/signal); 0: use state paper_wallet.goal_return_frac
      ANNA_PAPER_GOAL_FIXED_FRAC — optional clamp to one fraction in [0.05, 0.15] (disables adaptive stress)
      ANNA_GRADE12_MIN_NET_PNL_USD — require sum(pnl_usd) on cohort >= this
      ANNA_GRADE12_MIN_EQUITY_USD — require (start + net P&L) >= this (start env required)
      ANNA_GRADE12_MIN_BANKROLL_RETURN_FRAC — e.g. 0.05 requires 5% gain on start (start env required, >0)
    Env (tools bypass, tests/dev only):
      ANNA_SKIP_CURRICULUM_TOOLS_GATE=1 — ignore tool checklist (numeric only)
      ANNA_GRADE12_IGNORE_VACUOUS_WIN_STREAK=1 — do **not** fail numeric gate when every decisive row is won+0 P&L
        (dev only; production should leave unset so smoke-mode ledgers cannot pass as real performance)

    Order: tools must be complete before the 60% / min-N slice is considered for overall PASS.
    """
    min_wr = _env_float("ANNA_GRADE12_MIN_WIN_RATE", 0.6)
    min_decisive = _env_int("ANNA_GRADE12_MIN_DECISIVE_TRADES", 30)

    st = training_state if training_state is not None else load_state()
    merge_paper_wallet_into_state(st)
    if ensure_paper_wallet_clock(st):
        save_state(st)
    mastery = normalize_tool_mastery(st.get("grade_12_tool_mastery"))
    tools_ok = curriculum_tools_complete(mastery)
    missing_tools = missing_grade_12_tools(mastery)
    if _skip_curriculum_tools_gate():
        tools_ok = True
        missing_tools = []

    trades = load_paper_trades_for_gates()
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

    if tools_ok and not _ignore_vacuous_win_streak_gate():
        if cohort_is_vacuous_all_wins_zero_pnl(trades, min_decisive=min_decisive):
            numeric_blockers.append(
                "vacuous_win_streak_all_won_zero_pnl — ledger matches JACK_STUB_ALWAYS_WIN / "
                "JACK_STUB_SIMULATE=0 (smoke mode), not a scored cohort. Unset those vars and restart Karpathy."
            )

    total_pnl = float(s.total_pnl_usd)
    bankroll_start = resolve_paper_bankroll_start_usd(st)
    min_net_pnl = _env_optional_float("ANNA_GRADE12_MIN_NET_PNL_USD")
    min_equity = _env_optional_float("ANNA_GRADE12_MIN_EQUITY_USD")
    min_return_frac = _env_optional_float("ANNA_GRADE12_MIN_BANKROLL_RETURN_FRAC")
    equity_usd = bankroll_start + total_pnl
    pw = st.get("paper_wallet") or {}
    ag = compute_adaptive_paper_goal(bankroll_start=bankroll_start, paper_wallet=pw)
    goal_target_equity = float(ag["goal_target_equity_usd"])
    computed_goal_frac = float(ag["goal_return_frac"])
    goal_horizon_days = int(pw.get("goal_horizon_days") or DEFAULT_PAPER_WALLET["goal_horizon_days"])
    goal_days_elapsed = days_since_clock(pw.get("clock_start_utc"))
    paper_goal_met = bool(equity_usd >= goal_target_equity - 1e-9)

    if tools_ok:
        if min_net_pnl is not None and total_pnl < min_net_pnl:
            numeric_blockers.append(f"net_pnl_below_minimum ({total_pnl:.2f} < {min_net_pnl:.2f})")
        if min_equity is not None:
            if equity_usd < min_equity:
                numeric_blockers.append(f"equity_below_minimum ({equity_usd:.2f} < {min_equity:.2f})")
        if min_return_frac is not None:
            if bankroll_start <= 0:
                numeric_blockers.append(
                    "return_gate_requires_positive_bankroll (set ANNA_GRADE12_PAPER_BANKROLL_START_USD or paper_wallet.starting_usd)"
                )
            else:
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
        "paper_ledger_authoritative_for_training": PAPER_LEDGER_AUTHORITATIVE_FOR_TRAINING,
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
        "paper_goal_target_equity_usd": goal_target_equity,
        "paper_goal_return_frac": computed_goal_frac,
        "paper_goal_adaptive": bool(ag.get("adaptive")),
        "paper_goal_rationale": ag.get("rationale"),
        "paper_goal_stress_norm": ag.get("stress_norm"),
        "paper_goal_detail": ag.get("detail"),
        "paper_goal_horizon_days": goal_horizon_days,
        "paper_goal_days_elapsed": goal_days_elapsed,
        "paper_goal_met": paper_goal_met,
        "min_net_pnl_usd": min_net_pnl,
        "min_equity_usd": min_equity,
        "min_bankroll_return_frac": min_return_frac,
        "cohort_vacuous_all_wins_zero_pnl": bool(
            tools_ok
            and cohort_is_vacuous_all_wins_zero_pnl(trades, min_decisive=min_decisive)
        ),
        "blockers": blockers,
        "note": (
            "Pass requires curriculum tools in sequence (one focus at a time in the deck), then numeric paper cohort "
            "on the paper ledger (judgment-grade outcomes; no live venue settlement in this phase). "
            "RCS/RCA human sign-off may still apply per ANNA_GOES_TO_SCHOOL.md."
        ),
    }
