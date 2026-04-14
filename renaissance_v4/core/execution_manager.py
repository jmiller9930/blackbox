"""
execution_manager.py

Purpose:
Phase 6 paper execution: open trades with ATR-based stop/target, evaluate each bar with SL-first (pessimistic) same-bar rule.

Version:
v1.0

Change History:
- v1.0 Initial Phase 6 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.trade_state import TradeState

ATR_STOP_MULT = 1.6
ATR_TARGET_MULT = 4.0


class ExecutionManager:
    def __init__(self) -> None:
        self.current_trade: TradeState | None = None
        self.cumulative_pnl: float = 0.0

    def open_trade(
        self,
        symbol: str,
        price: float,
        direction: str,
        atr: float,
        size: float,
    ) -> None:
        atr_eff = max(atr, 1e-12)
        if direction == "long":
            stop = price - (ATR_STOP_MULT * atr_eff)
            target = price + (ATR_TARGET_MULT * atr_eff)
        else:
            stop = price + (ATR_STOP_MULT * atr_eff)
            target = price - (ATR_TARGET_MULT * atr_eff)

        self.current_trade = TradeState(
            symbol=symbol,
            entry_price=price,
            direction=direction,
            stop_loss=stop,
            take_profit=target,
            size=size,
        )

        print(f"[execution] OPEN {direction} @ {price} SL={stop} TP={target} size={size:.4f}")

    def evaluate_bar(self, high: float, low: float) -> tuple[str, float] | None:
        """
        Check stop before target (pessimistic when both are touched in the same bar).
        Returns (reason, exit_price) or None if still open.
        """
        if not self.current_trade or not self.current_trade.open:
            return None

        t = self.current_trade

        if t.direction == "long":
            if low <= t.stop_loss:
                t.open = False
                print("[execution] STOP LOSS HIT")
                return ("stop", t.stop_loss)
            if high >= t.take_profit:
                t.open = False
                print("[execution] TAKE PROFIT HIT")
                return ("target", t.take_profit)
        else:
            if high >= t.stop_loss:
                t.open = False
                print("[execution] STOP LOSS HIT")
                return ("stop", t.stop_loss)
            if low <= t.take_profit:
                t.open = False
                print("[execution] TAKE PROFIT HIT")
                return ("target", t.take_profit)

        return None
