"""
performance_metrics.py

Purpose:
Provide deterministic portfolio and signal-level performance calculations for RenaissanceV4.

Usage:
Imported by learning ledger and scorecard modules after trade outcomes are recorded.

Version:
v1.0

Change History:
- v1.0 Initial Phase 7 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.trade_state import TradeState


def compute_excursion_mae_mfe(trade: TradeState) -> tuple[float, float]:
    """
    Price-space MAE / MFE vs entry from observed bar min/low and max/high while trade was open.
    """
    if trade.min_low_seen is None or trade.max_high_seen is None:
        return 0.0, 0.0
    if trade.direction == "long":
        mae = max(0.0, trade.entry_price - trade.min_low_seen)
        mfe = max(0.0, trade.max_high_seen - trade.entry_price)
        return mae, mfe
    mae = max(0.0, trade.max_high_seen - trade.entry_price)
    mfe = max(0.0, trade.entry_price - trade.min_low_seen)
    return mae, mfe


def compute_summary_metrics(outcomes: list[OutcomeRecord]) -> dict:
    """
    Compute aggregate portfolio-style metrics from a list of completed outcomes.
    Returns a metrics dictionary with safe defaults when the list is empty.
    """
    if not outcomes:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "average_pnl": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "avg_mae": 0.0,
            "avg_mfe": 0.0,
        }

    total_trades = len(outcomes)
    wins = sum(1 for outcome in outcomes if outcome.pnl > 0)
    losses = sum(1 for outcome in outcomes if outcome.pnl <= 0)
    gross_pnl = sum(outcome.pnl for outcome in outcomes)
    net_pnl = gross_pnl
    average_pnl = gross_pnl / total_trades
    expectancy = average_pnl
    avg_mae = sum(outcome.mae for outcome in outcomes) / total_trades
    avg_mfe = sum(outcome.mfe for outcome in outcomes) / total_trades

    running_equity = 0.0
    equity_peak = 0.0
    max_drawdown = 0.0

    for outcome in outcomes:
        running_equity += outcome.pnl
        equity_peak = max(equity_peak, running_equity)
        drawdown = equity_peak - running_equity
        max_drawdown = max(max_drawdown, drawdown)

    win_rate = wins / total_trades if total_trades else 0.0

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "average_pnl": average_pnl,
        "expectancy": expectancy,
        "max_drawdown": max_drawdown,
        "avg_mae": avg_mae,
        "avg_mfe": avg_mfe,
    }


def recommend_lifecycle_state(total_trades: int, expectancy: float, max_drawdown: float) -> str:
    """
    Return a basic advisory lifecycle label from simple scorecard metrics.
    """
    if total_trades < 20:
        return "candidate"
    if max_drawdown > abs(expectancy) * 25 and total_trades >= 20:
        return "frozen"
    if expectancy < 0 and total_trades >= 50:
        return "reduced"
    if expectancy > 0 and total_trades >= 50:
        return "approved"
    return "probation"
