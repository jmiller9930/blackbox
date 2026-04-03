"""Grade 12 paper exit gates — measurable readiness from `paper_trades.jsonl` (no auto loop)."""

from __future__ import annotations

import os
from typing import Any

from modules.anna_training.paper_trades import load_paper_trades, summarize_trades


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


def evaluate_grade12_gates() -> dict[str, Any]:
    """Return PASS/FAIL vs env-tunable thresholds on decisive (won+lost) paper trades.

    Env:
      ANNA_GRADE12_MIN_WIN_RATE — default 0.6 (60% of decisive trades must be wins).
      ANNA_GRADE12_MIN_DECISIVE_TRADES — default 30 (minimum won+lost count before PASS allowed).

    Does not replace human graduation; emits auditable JSON for operators/scripts.
    """
    min_wr = _env_float("ANNA_GRADE12_MIN_WIN_RATE", 0.6)
    min_decisive = _env_int("ANNA_GRADE12_MIN_DECISIVE_TRADES", 30)

    trades = load_paper_trades()
    s = summarize_trades(trades)
    decisive = s.wins + s.losses
    wr = s.win_rate

    blockers: list[str] = []
    if decisive < min_decisive:
        blockers.append(f"decisive_trades_below_minimum ({decisive} < {min_decisive})")
    if wr is None or decisive == 0:
        blockers.append("no_decisive_trades")
    elif wr < min_wr:
        blockers.append(f"win_rate_below_minimum ({wr:.4f} < {min_wr})")

    ok = len(blockers) == 0
    return {
        "gate_id": "grade12_paper_win_rate_v1",
        "pass": ok,
        "min_win_rate": min_wr,
        "min_decisive_trades": min_decisive,
        "decisive_trades": decisive,
        "wins": s.wins,
        "losses": s.losses,
        "win_rate": wr,
        "total_trades_logged": s.trade_count,
        "blockers": blockers,
        "note": "RCS/RCA competence is separate; this gate is numeric paper cohort only.",
    }
