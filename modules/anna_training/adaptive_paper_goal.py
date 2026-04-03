"""Adaptive fictitious weekly goal: slide target return between min and max from recent market behavior.

Maps a stress score (0–1) to goal_return_frac in [GOAL_RETURN_MIN, GOAL_RETURN_MAX] so the bar is
not an arbitrary single number: quiet tape → lower stretch; wider movement / healthier feed → higher.
"""

from __future__ import annotations

import os
import sqlite3
import statistics
from pathlib import Path
from typing import Any

from modules.anna_training.paper_wallet import DEFAULT_PAPER_WALLET
from modules.anna_training.regime_signal import load_trading_core_signal

GOAL_RETURN_MIN = 0.05
GOAL_RETURN_MAX = 0.15

# Range of (max-min)/mean on recent primary prices — below → low stress, above → high stress.
_RANGE_PCT_SOFT = 0.002  # 0.20%
_RANGE_PCT_HARD = 0.06  # 6%


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _market_db_path() -> Path:
    env = (os.environ.get("BLACKBOX_MARKET_DATA_DB") or "").strip()
    if env:
        return Path(env).expanduser()
    return _repo_root() / "data" / "sqlite" / "market_data.db"


def _adaptive_enabled() -> bool:
    v = (os.environ.get("ANNA_PAPER_GOAL_ADAPTIVE") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _fixed_frac_override() -> float | None:
    raw = (os.environ.get("ANNA_PAPER_GOAL_FIXED_FRAC") or "").strip()
    if not raw:
        return None
    try:
        x = float(raw)
        return max(GOAL_RETURN_MIN, min(GOAL_RETURN_MAX, x))
    except ValueError:
        return None


def _stress_from_prices(prices: list[float]) -> tuple[float, dict[str, Any]]:
    """Return stress_norm in [0,1] and diagnostics."""
    p = [float(x) for x in prices if x is not None and float(x) > 0]
    meta: dict[str, Any] = {"tick_prices_used": len(p)}
    if len(p) < 5:
        return 0.5, {**meta, "reason": "insufficient_prices", "range_pct": None, "sigma_returns": None}

    lo, hi = min(p), max(p)
    mean_p = statistics.mean(p)
    range_pct = (hi - lo) / mean_p if mean_p > 0 else 0.0
    # Map range to 0–1
    span = _RANGE_PCT_HARD - _RANGE_PCT_SOFT
    stress = (range_pct - _RANGE_PCT_SOFT) / span if span > 0 else 0.5
    stress = max(0.0, min(1.0, float(stress)))

    rets: list[float] = []
    for i in range(1, len(p)):
        if p[i - 1] > 0:
            rets.append(p[i] / p[i - 1] - 1.0)
    sigma = float(statistics.pstdev(rets)) if len(rets) > 1 else 0.0
    # Blend: range is primary; sigma nudges (clip contribution)
    sigma_nudge = max(0.0, min(0.15, sigma * 25.0))
    stress = max(0.0, min(1.0, stress * 0.85 + sigma_nudge))

    meta.update(
        {
            "range_pct": round(range_pct, 6),
            "sigma_returns": round(sigma, 8),
            "reason": "from_recent_ticks",
        }
    )
    return stress, meta


def _stress_adjust_gate(stress: float, gate_state: str | None) -> float:
    gs = (gate_state or "").strip().lower()
    if gs in ("blocked",):
        return stress * 0.25
    if gs in ("degraded",):
        return max(0.0, min(1.0, stress * 0.8))
    return stress


def _stress_adjust_signal(stress: float, signal: dict[str, Any] | None) -> float:
    if not signal:
        return stress
    if signal.get("filters_pass") is False:
        return max(0.0, min(1.0, stress * 0.7))
    return stress


def compute_adaptive_paper_goal(
    *,
    symbol: str = "SOL-USD",
    bankroll_start: float = 100.0,
    paper_wallet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Returns goal_return_frac, goal_target_equity_usd, stress_norm, rationale, and diagnostics.

    When ANNA_PAPER_GOAL_ADAPTIVE=0, uses DEFAULT_PAPER_WALLET goal_return_frac (static).
    When ANNA_PAPER_GOAL_FIXED_FRAC is set, uses that (clamped to [5%, 15%]).
    """
    fixed = _fixed_frac_override()
    if fixed is not None:
        tgt = bankroll_start * (1.0 + fixed)
        return {
            "adaptive": False,
            "goal_return_frac": fixed,
            "goal_target_equity_usd": round(tgt, 4),
            "stress_norm": None,
            "rationale": f"fixed by ANNA_PAPER_GOAL_FIXED_FRAC={fixed:.4f}",
            "detail": {},
        }

    if not _adaptive_enabled():
        pw = paper_wallet if isinstance(paper_wallet, dict) else {}
        g = float(pw.get("goal_return_frac", DEFAULT_PAPER_WALLET["goal_return_frac"]))
        g = max(GOAL_RETURN_MIN, min(GOAL_RETURN_MAX, g))
        tgt = bankroll_start * (1.0 + g)
        return {
            "adaptive": False,
            "goal_return_frac": g,
            "goal_target_equity_usd": round(tgt, 4),
            "stress_norm": None,
            "rationale": "ANNA_PAPER_GOAL_ADAPTIVE=0 — using paper_wallet.goal_return_frac from state",
            "detail": {},
        }

    db_path = _market_db_path()
    prices: list[float] = []
    latest_gate: str | None = None
    if db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                rows = conn.execute(
                    """
                    SELECT primary_price, gate_state
                    FROM market_ticks
                    WHERE symbol = ? AND primary_price IS NOT NULL AND primary_price > 0
                    ORDER BY inserted_at DESC, id DESC
                    LIMIT 400
                    """,
                    (symbol,),
                ).fetchall()
            finally:
                conn.close()
            if rows:
                latest_gate = str(rows[0][1]) if rows[0][1] else None
                # chronological for range/vol
                for r in reversed(rows):
                    prices.append(float(r[0]))
        except OSError:
            pass

    stress, detail = _stress_from_prices(prices)
    stress = _stress_adjust_gate(stress, latest_gate)
    sig = load_trading_core_signal()
    stress = _stress_adjust_signal(stress, sig)

    g_frac = GOAL_RETURN_MIN + (GOAL_RETURN_MAX - GOAL_RETURN_MIN) * stress
    tgt = bankroll_start * (1.0 + g_frac)

    rationale = (
        f"adaptive {GOAL_RETURN_MIN:.0%}–{GOAL_RETURN_MAX:.0%} band; stress={stress:.3f} "
        f"from recent market_ticks ({symbol})"
    )
    if not prices:
        rationale = (
            f"no usable ticks in {db_path.name} — mid-stress fallback (stress=0.50 → "
            f"{(GOAL_RETURN_MIN + 0.5 * (GOAL_RETURN_MAX - GOAL_RETURN_MIN)):.1%} goal)"
        )
        stress = 0.5
        g_frac = GOAL_RETURN_MIN + (GOAL_RETURN_MAX - GOAL_RETURN_MIN) * stress
        tgt = bankroll_start * (1.0 + g_frac)
        detail = {**detail, "reason": "no_db_or_no_rows", "tick_prices_used": 0}

    return {
        "adaptive": True,
        "goal_return_frac": round(g_frac, 6),
        "goal_target_equity_usd": round(tgt, 4),
        "stress_norm": round(stress, 6),
        "rationale": rationale,
        "detail": detail,
        "latest_gate_state": latest_gate,
    }
