"""Per-strategy (and regime) cohort stats from ``paper_trades.jsonl`` for FACT lines and CLI."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from modules.anna_training.paper_trades import load_paper_trades_for_gates


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def min_n_for_strategy_stats() -> int:
    return _env_int("ANNA_STRATEGY_STATS_MIN_N", 5)


def compute_strategy_regime_stats(
    trades: list[dict[str, Any]] | None = None,
    *,
    min_n: int | None = None,
) -> list[dict[str, Any]]:
    """
    Group decisive trades (won+lost) by (strategy_label, regime).

    ``strategy_label`` empty → bucket ``_uncategorized``.
    ``regime`` empty/missing → ``_unknown``.
    """
    mn = min_n if min_n is not None else min_n_for_strategy_stats()
    rows = trades if trades is not None else load_paper_trades_for_gates()

    # key -> {wins, losses, pnl}
    agg: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0, 0, 0.0])

    for t in rows:
        if not isinstance(t, dict):
            continue
        res = str(t.get("result") or "").strip().lower()
        if res not in ("won", "lost"):
            continue
        sl = str(t.get("strategy_label") or "").strip() or "_uncategorized"
        reg = str(t.get("regime") or "").strip() or "_unknown"
        key = (sl, reg)
        if res == "won":
            agg[key][0] += 1
        else:
            agg[key][1] += 1
        agg[key][2] += float(t.get("pnl_usd") or 0)

    out: list[dict[str, Any]] = []
    for (sl, reg), (wins, losses, pnl) in sorted(agg.items()):
        decisive = wins + losses
        wr = (wins / decisive) if decisive else None
        out.append(
            {
                "strategy_label": sl,
                "regime": reg,
                "decisive_trades": decisive,
                "wins": wins,
                "losses": losses,
                "win_rate": round(wr, 4) if wr is not None else None,
                "total_pnl_usd": round(pnl, 6),
                "meets_min_n": decisive >= mn,
                "min_n_required": mn,
            }
        )
    return out


def strategy_stats_fact_lines(stats: list[dict[str, Any]] | None = None) -> list[str]:
    """Authoritative FACT lines for analyst path (descriptive only)."""
    s = stats if stats is not None else compute_strategy_regime_stats()
    lines: list[str] = []
    mn = min_n_for_strategy_stats()
    lines.append(
        f"FACT (strategy cohort): min_n={mn} for ranked stats; below min_n buckets are exploratory only."
    )
    shown = 0
    for row in s:
        if not row.get("meets_min_n"):
            continue
        sl = row.get("strategy_label")
        reg = row.get("regime")
        wr = row.get("win_rate")
        n = row.get("decisive_trades")
        pnl = row.get("total_pnl_usd")
        wr_s = f"{float(wr):.0%}" if wr is not None else "—"
        lines.append(
            f"FACT (strategy cohort): label={sl!s} regime={reg!s} decisive={n} win_rate={wr_s} total_pnl_usd={pnl}"
        )
        shown += 1
        if shown >= 8:
            break
    if shown == 0:
        lines.append(
            "FACT (strategy cohort): no (strategy, regime) bucket meets min_n yet — keep logging labeled paper rows."
        )
    return lines
