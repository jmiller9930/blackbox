"""
execution_manager.py

Purpose:
Phase 6 paper execution: open trades with ATR-based stop/target, evaluate each bar with SL-first (pessimistic) same-bar rule.

Version:
v1.1

Change History:
- v1.0 Initial Phase 6 implementation.
- v1.1 Phase 7: entry metadata, bar excursions for MAE/MFE, record_bar_extremes.
- v1.2 DV-ARCH-CORRECTION-013: ATR stop/target geometry; entry_regime on open.
"""

from __future__ import annotations

from renaissance_v4.core.trade_state import TradeState

# DV-ARCH-CORRECTION-013: diagnostic_quality_v1 showed stop exits with avg MAE > avg MFE and
# ~72% stop vs ~28% target — geometry favored stop-outs. Widen stop slightly, bring target closer
# to improve target hit rate vs premature stops (reward/risk in ATR units ~1.88 vs prior ~2.5).
ATR_STOP_MULT = 1.78
ATR_TARGET_MULT = 3.35


class ExecutionManager:
    def __init__(
        self,
        *,
        atr_stop_mult: float | None = None,
        atr_target_mult: float | None = None,
    ) -> None:
        self.atr_stop_mult = float(ATR_STOP_MULT if atr_stop_mult is None else atr_stop_mult)
        self.atr_target_mult = float(ATR_TARGET_MULT if atr_target_mult is None else atr_target_mult)
        self.current_trade: TradeState | None = None
        self.cumulative_pnl: float = 0.0

    def open_trade(
        self,
        symbol: str,
        price: float,
        direction: str,
        atr: float,
        size: float,
        entry_time: int,
        contributing_signal_names: list[str],
        size_tier: str,
        notional_fraction: float,
        bar_high: float,
        bar_low: float,
        entry_regime: str = "unknown",
    ) -> None:
        atr_eff = max(atr, 1e-12)
        sm = self.atr_stop_mult
        tm = self.atr_target_mult
        if direction == "long":
            stop = price - (sm * atr_eff)
            target = price + (tm * atr_eff)
        else:
            stop = price + (sm * atr_eff)
            target = price - (tm * atr_eff)

        self.current_trade = TradeState(
            symbol=symbol,
            entry_price=price,
            direction=direction,
            stop_loss=stop,
            take_profit=target,
            size=size,
            entry_time=entry_time,
            contributing_signal_names=list(contributing_signal_names),
            risk_size_tier=size_tier,
            risk_notional_fraction=notional_fraction,
            entry_regime=entry_regime,
            min_low_seen=bar_low,
            max_high_seen=bar_high,
        )

        print(f"[execution] OPEN {direction} @ {price} SL={stop} TP={target} size={size:.4f}")

    def record_bar_extremes(self, high: float, low: float) -> None:
        """
        Update running min/max bar range while a position is open (for MAE/MFE).
        """
        if not self.current_trade or not self.current_trade.open:
            return
        t = self.current_trade
        if t.min_low_seen is None or t.max_high_seen is None:
            t.min_low_seen = low
            t.max_high_seen = high
            return
        t.min_low_seen = min(t.min_low_seen, low)
        t.max_high_seen = max(t.max_high_seen, high)

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
