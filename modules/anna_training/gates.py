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


def _skip_curriculum_tools_gate() -> bool:
    return (os.environ.get("ANNA_SKIP_CURRICULUM_TOOLS_GATE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def evaluate_grade12_gates() -> dict[str, Any]:
    """Return PASS/FAIL: (1) all Grade 12 curriculum tools passed, (2) numeric paper cohort.

    Env (numeric):
      ANNA_GRADE12_MIN_WIN_RATE — default 0.6
      ANNA_GRADE12_MIN_DECISIVE_TRADES — default 30
    Env (tools bypass, tests/dev only):
      ANNA_SKIP_CURRICULUM_TOOLS_GATE=1 — ignore tool checklist (numeric only)

    Order: tools must be complete before the 60% / min-N slice is considered for overall PASS.
    """
    min_wr = _env_float("ANNA_GRADE12_MIN_WIN_RATE", 0.6)
    min_decisive = _env_int("ANNA_GRADE12_MIN_DECISIVE_TRADES", 30)

    st = load_state()
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
        "blockers": blockers,
        "note": "Pass requires curriculum tools in sequence (one focus at a time in the deck), then numeric paper cohort. RCS/RCA human sign-off may still apply per ANNA_GOES_TO_SCHOOL.md.",
    }
