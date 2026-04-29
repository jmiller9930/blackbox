"""
GT056 — Opportunity selection metrics (selection quality vs raw win rate).

Uses **Referee** ``pnl`` on ``student_learning_record_v1`` rows together with sealed
``student_action_v1`` (enter_long / enter_short / no_trade).

* **Taken** = directional trade chosen.
* **Skipped** = ``no_trade``.
* **bad_trades_avoided** = skipped rows where Referee PnL is negative (would have lost).
* **good_trades_missed** = skipped rows where Referee PnL is positive (would have won).
"""

from __future__ import annotations

from typing import Any

SCHEMA_OPPORTUNITY_SELECTION_METRICS_V1 = "opportunity_selection_metrics_v1"


def compute_opportunity_selection_metrics_v1(
    learning_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Aggregate metrics over learning rows that include ``referee_outcome_subset.pnl`` and
    ``student_output.student_action_v1``.
    """
    rows: list[tuple[float, str]] = []
    for rec in learning_records:
        if not isinstance(rec, dict):
            continue
        sub = rec.get("referee_outcome_subset")
        if not isinstance(sub, dict) or "pnl" not in sub:
            continue
        try:
            pnl = float(sub.get("pnl"))
        except (TypeError, ValueError):
            continue
        so = rec.get("student_output")
        if not isinstance(so, dict):
            continue
        act = str(so.get("student_action_v1") or "").strip().lower()
        if act not in ("enter_long", "enter_short", "no_trade"):
            continue
        rows.append((pnl, act))

    n = len(rows)
    taken = [(p, a) for p, a in rows if a in ("enter_long", "enter_short")]
    skipped = [(p, a) for p, a in rows if a == "no_trade"]

    trades_taken = len(taken)
    trades_skipped = len(skipped)

    wins_taken = sum(1 for p, _ in taken if p > 0.0)
    losses_taken = sum(1 for p, _ in taken if p < 0.0)
    wins_skipped = sum(1 for p, _ in skipped if p > 0.0)
    losses_skipped = sum(1 for p, _ in skipped if p < 0.0)

    bad_trades_avoided = losses_skipped
    good_trades_missed = wins_skipped

    sum_pnl_all = sum(p for p, _ in rows)
    sum_pnl_taken = sum(p for p, _ in taken)

    taken_pnls_pos = [p for p, _ in taken if p > 0.0]
    taken_pnls_neg = [p for p, _ in taken if p < 0.0]

    avg_win = sum(taken_pnls_pos) / len(taken_pnls_pos) if taken_pnls_pos else None
    avg_loss = sum(taken_pnls_neg) / len(taken_pnls_neg) if taken_pnls_neg else None

    taken_win_rate = (wins_taken / trades_taken) if trades_taken else None
    wins_all = sum(1 for p, _ in rows if p > 0.0)
    opportunity_win_rate = (wins_all / n) if n else None
    selection_rate = (trades_taken / n) if n else None

    expectancy_per_taken_trade = (sum_pnl_taken / trades_taken) if trades_taken else None
    expectancy_per_possible_setup = (sum_pnl_all / n) if n else None

    def _r(x: float | None) -> float | None:
        return None if x is None else round(float(x), 10)

    return {
        "schema": SCHEMA_OPPORTUNITY_SELECTION_METRICS_V1,
        "contract_version": 1,
        "total_possible_setups": int(n),
        "trades_taken": int(trades_taken),
        "trades_skipped": int(trades_skipped),
        "wins_taken": int(wins_taken),
        "losses_taken": int(losses_taken),
        "wins_skipped": int(wins_skipped),
        "losses_skipped": int(losses_skipped),
        "bad_trades_avoided": int(bad_trades_avoided),
        "good_trades_missed": int(good_trades_missed),
        "taken_win_rate": _r(taken_win_rate),
        "opportunity_win_rate": _r(opportunity_win_rate),
        "selection_rate": _r(selection_rate),
        "avg_win": _r(avg_win),
        "avg_loss": _r(avg_loss),
        "expectancy_per_taken_trade": _r(expectancy_per_taken_trade),
        "expectancy_per_possible_setup": _r(expectancy_per_possible_setup),
    }


__all__ = [
    "SCHEMA_OPPORTUNITY_SELECTION_METRICS_V1",
    "compute_opportunity_selection_metrics_v1",
]
