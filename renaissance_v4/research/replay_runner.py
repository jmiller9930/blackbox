"""
replay_runner.py

Purpose:
Run a deterministic bar-by-bar replay over historical 5-minute bars.

Usage:
Run after Phases 1 through 6 are installed to validate the full pipeline including paper execution simulation.

Version:
v6.0

Change History:
- v1.0 Initial Phase 1 replay shell.
- v2.0 Added MarketState builder, feature engine, and regime classifier integration.
- v3.0 Added signal evaluation layer integration.
- v4.0 Added fusion engine integration and no-trade threshold logic.
- v5.0 Added risk governor integration and execution gating.
- v6.0 Added execution manager, stop/target simulation, and PnL tracking.
"""

from __future__ import annotations

import uuid

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.core.execution_manager import ExecutionManager
from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.fusion_engine import fuse_signal_results
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.pnl import compute_pnl
from renaissance_v4.core.regime_classifier import classify_regime
from renaissance_v4.core.risk_governor import evaluate_risk
from renaissance_v4.signals.breakout_expansion import BreakoutExpansionSignal
from renaissance_v4.signals.mean_reversion_fade import MeanReversionFadeSignal
from renaissance_v4.signals.pullback_continuation import PullbackContinuationSignal
from renaissance_v4.signals.trend_continuation import TrendContinuationSignal
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50


def main() -> None:
    """
    Iterate through historical bars in strict chronological order.
    Build MarketState, FeatureSet, regime, signals, fusion, risk, then manage simulated positions and opens.
    """
    connection = get_connection()
    rows = connection.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m
        ORDER BY open_time ASC
        """
    ).fetchall()

    print(f"[replay] Loaded {len(rows)} bars")

    if len(rows) < MIN_ROWS_REQUIRED:
        raise RuntimeError(
            f"[replay] Need at least {MIN_ROWS_REQUIRED} bars, found {len(rows)}"
        )

    signals = [
        TrendContinuationSignal(),
        PullbackContinuationSignal(),
        BreakoutExpansionSignal(),
        MeanReversionFadeSignal(),
    ]

    exec_manager = ExecutionManager()
    processed = 0

    for index in range(MIN_ROWS_REQUIRED, len(rows) + 1):
        window = rows[:index]
        state = build_market_state(window)
        features = build_feature_set(state)
        regime = classify_regime(features)

        signal_results = []
        for signal in signals:
            result = signal.evaluate(state, features, regime)
            signal_results.append(result)

        fusion_result = fuse_signal_results(signal_results)

        drawdown_proxy = 0.0

        risk_decision = evaluate_risk(
            fusion_result=fusion_result,
            features=features,
            regime=regime,
            drawdown_proxy=drawdown_proxy,
        )

        confidence_score = fusion_result.fusion_score
        edge_score = max(fusion_result.long_score, fusion_result.short_score)

        exit_this_bar: dict | None = None
        if exec_manager.current_trade and exec_manager.current_trade.open:
            t = exec_manager.current_trade
            entry_price = t.entry_price
            trade_direction = t.direction
            trade_size = t.size
            exit_ev = exec_manager.evaluate_bar(state.current_high, state.current_low)
            if exit_ev:
                reason, exit_price = exit_ev
                bar_pnl = compute_pnl(entry_price, exit_price, trade_size, trade_direction)
                exec_manager.cumulative_pnl += bar_pnl
                print(
                    f"[execution] bar_pnl={bar_pnl:.6f} cumulative_pnl={exec_manager.cumulative_pnl:.6f}"
                )
                exit_this_bar = {
                    "reason": reason,
                    "exit_price": exit_price,
                    "bar_pnl": bar_pnl,
                }

        flat = exec_manager.current_trade is None or not exec_manager.current_trade.open
        opened_this_bar = False
        if (
            flat
            and risk_decision.allowed
            and fusion_result.direction in {"long", "short"}
        ):
            exec_manager.open_trade(
                symbol=state.symbol,
                price=state.current_close,
                direction=fusion_result.direction,
                atr=features.atr_proxy_14,
                size=risk_decision.notional_fraction,
            )
            opened_this_bar = True

        position_open_after = (
            exec_manager.current_trade is not None and exec_manager.current_trade.open
        )

        decision = DecisionContract(
            decision_id=str(uuid.uuid4()),
            symbol=state.symbol,
            timestamp=state.timestamp,
            market_regime=regime,
            direction=fusion_result.direction,
            fusion_score=fusion_result.fusion_score,
            confidence_score=confidence_score,
            edge_score=edge_score,
            risk_budget=risk_decision.notional_fraction,
            execution_allowed=risk_decision.allowed,
            reason_trace={
                "phase": "phase_6_execution_simulation",
                "regime": regime,
                "fusion": {
                    "direction": fusion_result.direction,
                    "long_score": fusion_result.long_score,
                    "short_score": fusion_result.short_score,
                    "gross_score": fusion_result.gross_score,
                    "conflict_score": fusion_result.conflict_score,
                    "overlap_penalty": fusion_result.overlap_penalty,
                    "threshold_passed": fusion_result.threshold_passed,
                },
                "risk": {
                    "allowed": risk_decision.allowed,
                    "size_tier": risk_decision.size_tier,
                    "notional_fraction": risk_decision.notional_fraction,
                    "compression_factor": risk_decision.compression_factor,
                    "veto_reasons": risk_decision.veto_reasons,
                    "debug_trace": risk_decision.debug_trace,
                },
                "execution": {
                    "exit_this_bar": exit_this_bar,
                    "opened_this_bar": opened_this_bar,
                    "cumulative_pnl": exec_manager.cumulative_pnl,
                    "position_open_after": position_open_after,
                },
                "contributing_signals": fusion_result.contributing_signals,
                "suppressed_signals": fusion_result.suppressed_signals,
            },
        )

        processed += 1

        if processed % 5000 == 0:
            print(
                "[replay] Progress "
                f"processed={processed} timestamp={decision.timestamp} "
                f"regime={decision.market_regime} direction={decision.direction} "
                f"risk_budget={decision.risk_budget:.2f} "
                f"execution_allowed={decision.execution_allowed} "
                f"cumulative_pnl={exec_manager.cumulative_pnl:.6f}"
            )

    print("[replay] Phase 6 replay completed successfully")


if __name__ == "__main__":
    main()
