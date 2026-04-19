"""
Pattern outcome quality v1 — deterministic metrics from closed-trade outcomes (replay ledger).

Used by scenario ``goal_v2`` / operator harness: **not** raw win-rate optimization or PnL targets;
emphasizes expectancy, win/loss *sizes*, and exit behavior vs MFE/MAE.
"""

from __future__ import annotations

from typing import Any

_EPS = 1e-12


def compute_pattern_outcome_quality_v1(outcomes: list[Any]) -> dict[str, Any]:
    """
    Machine-evaluable outcome quality from :class:`~renaissance_v4.core.outcome_record.OutcomeRecord` list.

    * **expectancy_per_trade** — mean PnL (same scale as ledger ``expectancy`` when all rows are trades).
    * **avg_win_size** — mean PnL over winning trades.
    * **avg_loss_size** — mean |PnL| over losing / flat trades.
    * **win_loss_size_ratio** — avg_win_size / avg_loss_size (``None`` if no losses to size against).
    * **exit_efficiency** — mean per-trade score in ``[0, 1]``: wins use ``min(1, pnl/mfe)`` when MFE > 0;
      losses use ``1 - min(1, |pnl|/mae)`` when MAE > 0 (higher = smaller loss vs worst adverse excursion).
    """
    if not outcomes:
        return {
            "expectancy_per_trade": 0.0,
            "avg_win_size": 0.0,
            "avg_loss_size": 0.0,
            "win_loss_size_ratio": None,
            "exit_efficiency": 0.0,
            "wins_count": 0,
            "losses_count": 0,
            "trades_count": 0,
        }

    pnls = [float(o.pnl) for o in outcomes]
    n = len(pnls)
    expectancy = sum(pnls) / n

    wins = [o for o in outcomes if float(o.pnl) > 0.0]
    losses = [o for o in outcomes if float(o.pnl) <= 0.0]
    aw = sum(float(o.pnl) for o in wins) / len(wins) if wins else 0.0
    al = sum(abs(float(o.pnl)) for o in losses) / len(losses) if losses else 0.0
    wl_ratio = (aw / al) if al > _EPS else None

    scores: list[float] = []
    for o in outcomes:
        pnl = float(o.pnl)
        mfe = max(0.0, float(o.mfe))
        mae = max(0.0, float(o.mae))
        if pnl > 0.0:
            if mfe > _EPS:
                scores.append(min(1.0, pnl / mfe))
            else:
                scores.append(1.0)
        else:
            if mae > _EPS:
                scores.append(max(0.0, min(1.0, 1.0 - min(1.0, abs(pnl) / mae))))
            else:
                scores.append(0.0)

    exit_eff = sum(scores) / len(scores) if scores else 0.0

    return {
        "expectancy_per_trade": round(expectancy, 6),
        "avg_win_size": round(aw, 6),
        "avg_loss_size": round(al, 6),
        "win_loss_size_ratio": None if wl_ratio is None else round(wl_ratio, 6),
        "exit_efficiency": round(exit_eff, 6),
        "wins_count": len(wins),
        "losses_count": len(losses),
        "trades_count": n,
    }


def diff_outcome_quality_v1(
    control: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Per-field deltas (candidate minus control) for harness / proof."""
    out: dict[str, Any] = {}
    for k in (
        "expectancy_per_trade",
        "avg_win_size",
        "avg_loss_size",
        "exit_efficiency",
    ):
        out[f"{k}_delta"] = round(float(candidate[k]) - float(control[k]), 6)
    c0 = control.get("win_loss_size_ratio")
    c1 = candidate.get("win_loss_size_ratio")
    if c0 is not None and c1 is not None:
        out["win_loss_size_ratio_delta"] = round(float(c1) - float(c0), 6)
    else:
        out["win_loss_size_ratio_delta"] = None
    return out


DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY: dict[str, Any] = {
    "goal_name": "pattern_outcome_quality",
    "objective_type": "outcome_quality",
    "primary_metric": "expectancy_per_trade",
    "secondary_metrics": [
        "avg_win_size",
        "avg_loss_size",
        "win_loss_size_ratio",
        "exit_efficiency",
    ],
    "constraints": {
        "minimum_trade_count": 5,
        "maximum_drawdown_threshold": None,
    },
    "notes": {
        "intent_plain": (
            "Improve pattern recognition so trades capture more of favorable moves and keep losses "
            "smaller through better timing — not maximizing raw win count or a fixed PnL target."
        ),
        "evaluation_focus": (
            "Optimize outcome quality metrics derived from pattern-aware behavior; engine remains neutral."
        ),
    },
}


__all__ = [
    "DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY",
    "compute_pattern_outcome_quality_v1",
    "diff_outcome_quality_v1",
]
