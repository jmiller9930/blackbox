"""
execution_learning_bridge.py

Purpose:
SINGLE allowed path: ExecutionManager closed trade → OutcomeRecord → LearningLedger.

Do not construct OutcomeRecord for the ledger elsewhere.

Version:
v1.0

Change History:
- v1.0 Baseline v1 acceptance (architect).
"""

from __future__ import annotations

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.trade_state import TradeState
from renaissance_v4.research.determinism import deterministic_trade_id
from renaissance_v4.research.learning_ledger import LearningLedger


def record_closed_trade_to_ledger(
    ledger: LearningLedger,
    *,
    closed_trade: TradeState,
    exit_time: int,
    exit_price: float,
    exit_reason: str,
    bar_pnl: float,
    mae: float,
    mfe: float,
    regime: str,
) -> OutcomeRecord:
    """
    Record one completed simulated trade. PnL must already match compute_pnl(entry, exit, size, direction).
    """
    trade_id = deterministic_trade_id(
        closed_trade.symbol,
        closed_trade.entry_time,
        exit_time,
        closed_trade.entry_price,
        exit_price,
        closed_trade.direction,
    )
    outcome = OutcomeRecord(
        trade_id=trade_id,
        symbol=closed_trade.symbol,
        direction=closed_trade.direction,
        entry_time=closed_trade.entry_time,
        exit_time=exit_time,
        entry_price=closed_trade.entry_price,
        exit_price=exit_price,
        pnl=bar_pnl,
        mae=mae,
        mfe=mfe,
        exit_reason=exit_reason,
        contributing_signals=list(closed_trade.contributing_signal_names),
        regime=regime,
        size_tier=closed_trade.risk_size_tier,
        notional_fraction=closed_trade.risk_notional_fraction,
        metadata={
            "stop_loss": closed_trade.stop_loss,
            "take_profit": closed_trade.take_profit,
            "pipeline": "ExecutionManager→TradeState→close→OutcomeRecord→LearningLedger",
        },
    )
    ledger.record_outcome(outcome)
    return outcome
