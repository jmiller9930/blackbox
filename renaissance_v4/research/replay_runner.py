"""
replay_runner.py

Purpose:
Run a deterministic bar-by-bar replay over historical 5-minute bars.

Usage:
Run directly after Phases 1 through 3 are installed to validate the market-state, feature, regime, and signal pipeline.

Version:
v3.0

Change History:
- v1.0 Initial Phase 1 replay shell.
- v2.0 Added MarketState builder, feature engine, and regime classifier integration.
- v3.0 Added signal evaluation layer integration.
"""

from __future__ import annotations

import uuid

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.regime_classifier import classify_regime
from renaissance_v4.signals.breakout_expansion import BreakoutExpansionSignal
from renaissance_v4.signals.mean_reversion_fade import MeanReversionFadeSignal
from renaissance_v4.signals.pullback_continuation import PullbackContinuationSignal
from renaissance_v4.signals.trend_continuation import TrendContinuationSignal
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50


def main() -> None:
    """
    Iterate through historical bars in strict chronological order.
    Build MarketState, FeatureSet, regime, and signal outputs for each eligible replay step.
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

    processed = 0

    for index in range(MIN_ROWS_REQUIRED, len(rows) + 1):
        window = rows[:index]
        state = build_market_state(window)
        features = build_feature_set(state)
        regime = classify_regime(features)

        signal_results = []
        active_signals = []
        suppressed_signals = []

        for signal in signals:
            result = signal.evaluate(state, features, regime)
            signal_results.append(result)
            if result.active:
                active_signals.append(result.signal_name)
            else:
                suppressed_signals.append(
                    f"{result.signal_name}:{result.suppression_reason}"
                )

        decision = DecisionContract(
            decision_id=str(uuid.uuid4()),
            symbol=state.symbol,
            timestamp=state.timestamp,
            market_regime=regime,
            direction="no_trade",
            fusion_score=0.0,
            confidence_score=0.0,
            edge_score=0.0,
            risk_budget=0.0,
            execution_allowed=False,
            reason_trace={
                "phase": "phase_3_signal_architecture",
                "regime": regime,
                "active_signals": active_signals,
                "suppressed_signals": suppressed_signals,
                "signal_count": len(signal_results),
            },
        )

        processed += 1

        if processed % 5000 == 0:
            print(
                "[replay] Progress "
                f"processed={processed} "
                f"timestamp={decision.timestamp} "
                f"regime={decision.market_regime} "
                f"active_signals={active_signals}"
            )

    print("[replay] Phase 3 replay completed successfully")


if __name__ == "__main__":
    main()
