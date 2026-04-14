# RenaissanceV4 — Phase 7 Code Pack
**System:** BlackBox  
**Authority:** Architect  
**Purpose:** Phase 7 implementation for performance metrics, learning ledger, and signal lifecycle scoring  
**Scope:** Outcome recording, scorecards, drawdown tracking, win/loss analytics, and learning-loop foundations  
**Status:** Build after Phase 6 passes

---

# 1. Objective

Phase 7 is where RenaissanceV4 starts learning from consequences.

Before Phase 7, the machine can:

- ingest data
- interpret market state
- generate signals
- fuse evidence
- govern risk
- simulate trade lifecycle

But it still does not **retain judgment** about what worked.

Phase 7 adds the first real learning layer:

- record every completed trade outcome
- measure win rate, expectancy, and drawdown
- track MAE and MFE
- build per-signal scorecards
- create the first promotion / reduction / freeze hooks

This is still not full self-improvement.

It is the foundation that makes self-improvement possible.

---

# 2. What Phase 7 Includes

Phase 7 includes only:

1. `OutcomeRecord` dataclass  
2. `performance_metrics.py`  
3. `learning_ledger.py`  
4. `signal_scorecard.py`  
5. replay integration for completed trade outcomes  
6. rolling performance metrics  
7. drawdown tracking  
8. basic lifecycle state recommendation hooks  

Phase 7 does **not** include:

- automatic promotion execution
- automatic signal retirement enforcement
- live capital deployment
- portfolio rotation
- research hypothesis generation

Those come later.

---

# 3. Folder Structure Additions

```text
renaissance_v4/
├── core/
│   ├── ...
│   ├── outcome_record.py
│   └── performance_metrics.py
├── research/
│   ├── learning_ledger.py
│   ├── replay_runner.py
│   └── signal_scorecard.py
└── signals/
    └── ...
```

---

# 4. Build Order

Build in this exact order:

1. `core/outcome_record.py`
2. `core/performance_metrics.py`
3. `research/learning_ledger.py`
4. `research/signal_scorecard.py`
5. update `research/replay_runner.py`

Do not start promotion-board automation before this phase passes cleanly.

---

# 5. Phase 7 Design Rules

1. Every closed trade must become a persistent outcome record.
2. No learning may be inferred from open trades.
3. Performance must be measured after friction-aware trade results.
4. Scorecards must be explainable from stored outcomes.
5. Learning must prefer honesty over optimism.
6. Weak sample sizes must remain weak; do not over-interpret small N.
7. Drawdown tracking is mandatory.
8. Signal lifecycle hints must be advisory first, not auto-enforced.

---

# 6. Minimum Metrics Required

Phase 7 must compute at minimum:

- total trades
- wins
- losses
- win rate
- gross pnl
- net pnl
- average pnl
- expectancy
- max drawdown
- MAE average
- MFE average

Per signal family, track:

- sample count
- win rate
- expectancy
- average MAE
- average MFE
- suggested lifecycle state

---

# 7. Lifecycle Recommendation Model

Phase 7 introduces recommendation-only lifecycle labels:

- `candidate`
- `probation`
- `approved`
- `reduced`
- `frozen`

These are not yet fully automatic governance states.

They are scorecard outputs based on metrics.

Suggested default interpretation:

- fewer than 20 trades → `candidate`
- 20 to 49 trades with mixed results → `probation`
- 50+ trades and positive expectancy → `approved`
- negative expectancy with enough sample → `reduced`
- severe drawdown or repeated underperformance → `frozen`

These thresholds are starting points, not permanent truth.

---

# 8. CAT Blocks

## 8.1 Create `renaissance_v4/core/outcome_record.py`

```bash
cat > renaissance_v4/core/outcome_record.py << 'EOF'
"""
outcome_record.py

Purpose:
Define the canonical OutcomeRecord object for completed RenaissanceV4 trades.

Usage:
Created when a simulated trade closes and consumed by learning ledger and scorecard logic.

Version:
v1.0

Change History:
- v1.0 Initial Phase 7 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutcomeRecord:
    """
    Canonical completed-trade record for learning and performance measurement.
    """
    trade_id: str
    symbol: str
    direction: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    pnl: float
    mae: float
    mfe: float
    exit_reason: str
    contributing_signals: list[str] = field(default_factory=list)
    regime: str = "unknown"
    size_tier: str = "zero"
    notional_fraction: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
EOF
```

---

## 8.2 Create `renaissance_v4/core/performance_metrics.py`

```bash
cat > renaissance_v4/core/performance_metrics.py << 'EOF'
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
EOF
```

---

## 8.3 Create `renaissance_v4/research/learning_ledger.py`

```bash
cat > renaissance_v4/research/learning_ledger.py << 'EOF'
"""
learning_ledger.py

Purpose:
Store completed RenaissanceV4 trade outcomes in memory during replay and expose summary metrics.

Usage:
Instantiated by replay logic to accumulate outcomes and compute portfolio-level learning metrics.

Version:
v1.0

Change History:
- v1.0 Initial Phase 7 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.performance_metrics import compute_summary_metrics


class LearningLedger:
    """
    In-memory outcome ledger for replay-time learning analysis.
    """

    def __init__(self) -> None:
        self.outcomes: list[OutcomeRecord] = []

    def record_outcome(self, outcome: OutcomeRecord) -> None:
        """
        Append a completed outcome record to the ledger and print a visible confirmation.
        """
        self.outcomes.append(outcome)
        print(
            f"[learning_ledger] Recorded outcome trade_id={outcome.trade_id} "
            f"pnl={outcome.pnl:.4f} exit_reason={outcome.exit_reason}"
        )

    def summary(self) -> dict:
        """
        Return current aggregate metrics across all recorded outcomes.
        """
        metrics = compute_summary_metrics(self.outcomes)
        print(f"[learning_ledger] Summary metrics: {metrics}")
        return metrics
EOF
```

---

## 8.4 Create `renaissance_v4/research/signal_scorecard.py`

```bash
cat > renaissance_v4/research/signal_scorecard.py << 'EOF'
"""
signal_scorecard.py

Purpose:
Build per-signal-family scorecards from completed RenaissanceV4 outcomes.

Usage:
Used after replay to summarize which signal families performed well or poorly.

Version:
v1.0

Change History:
- v1.0 Initial Phase 7 implementation.
"""

from __future__ import annotations

from collections import defaultdict

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.performance_metrics import compute_summary_metrics, recommend_lifecycle_state


def build_signal_scorecards(outcomes: list[OutcomeRecord]) -> dict[str, dict]:
    """
    Group outcomes by contributing signal name and return a scorecard per signal.
    """
    grouped: dict[str, list[OutcomeRecord]] = defaultdict(list)

    for outcome in outcomes:
        for signal_name in outcome.contributing_signals:
            grouped[signal_name].append(outcome)

    scorecards: dict[str, dict] = {}

    for signal_name, signal_outcomes in grouped.items():
        metrics = compute_summary_metrics(signal_outcomes)
        lifecycle_state = recommend_lifecycle_state(
            total_trades=metrics["total_trades"],
            expectancy=metrics["expectancy"],
            max_drawdown=metrics["max_drawdown"],
        )
        scorecards[signal_name] = {
            **metrics,
            "lifecycle_state": lifecycle_state,
        }
        print(f"[signal_scorecard] signal={signal_name} scorecard={scorecards[signal_name]}")

    return scorecards
EOF
```

---

## 8.5 Update `renaissance_v4/research/replay_runner.py`

```bash
cat > renaissance_v4/research/replay_runner.py << 'EOF'
"""
replay_runner.py

Purpose:
Run a deterministic bar-by-bar replay over historical 5-minute bars.

Usage:
Run directly after Phases 1 through 7 are installed to validate market-state, feature, regime, signal, fusion, risk, execution, and learning logic.

Version:
v7.0

Change History:
- v1.0 Initial Phase 1 replay shell.
- v2.0 Added MarketState builder, feature engine, and regime classifier integration.
- v3.0 Added signal evaluation layer integration.
- v4.0 Added fusion engine integration and no-trade threshold logic.
- v5.0 Added risk governor integration and execution gating.
- v6.0 Added execution simulation and trade lifecycle hooks.
- v7.0 Added learning ledger and scorecard generation.
"""

from __future__ import annotations

from collections import deque
import uuid

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.fusion_engine import fuse_signal_results
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.regime_classifier import classify_regime
from renaissance_v4.core.risk_governor import evaluate_risk
from renaissance_v4.research.learning_ledger import LearningLedger
from renaissance_v4.research.signal_scorecard import build_signal_scorecards
from renaissance_v4.signals.breakout_expansion import BreakoutExpansionSignal
from renaissance_v4.signals.mean_reversion_fade import MeanReversionFadeSignal
from renaissance_v4.signals.pullback_continuation import PullbackContinuationSignal
from renaissance_v4.signals.trend_continuation import TrendContinuationSignal
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50


def main() -> None:
    """
    Iterate through historical bars in strict chronological order.
    This Phase 7 draft assumes prior execution simulation code can provide closed-trade events.
    For now, it demonstrates how completed outcomes would be recorded and summarized.
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

    ledger = LearningLedger()

    processed = 0
    recently_active_signals: deque[list[str]] = deque(maxlen=5)

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

        active_signals = [result.signal_name for result in signal_results if result.active]
        recently_active_signals.append(active_signals)

        decision = DecisionContract(
            decision_id=str(uuid.uuid4()),
            symbol=state.symbol,
            timestamp=state.timestamp,
            market_regime=regime,
            direction=fusion_result.direction,
            fusion_score=fusion_result.fusion_score,
            confidence_score=fusion_result.fusion_score,
            edge_score=max(fusion_result.long_score, fusion_result.short_score),
            risk_budget=risk_decision.notional_fraction,
            execution_allowed=risk_decision.allowed,
            reason_trace={
                "phase": "phase_7_learning_foundation",
                "regime": regime,
                "active_signals": active_signals,
                "risk_allowed": risk_decision.allowed,
                "size_tier": risk_decision.size_tier,
            },
        )

        # Placeholder outcome generation hook:
        # Replace this in real Phase 7 integration with actual closed trades from Phase 6 lifecycle engine.
        if processed > 0 and processed % 10000 == 0 and active_signals:
            synthetic_pnl = 1.25 if fusion_result.direction != "no_trade" else -0.50
            outcome = OutcomeRecord(
                trade_id=str(uuid.uuid4()),
                symbol=state.symbol,
                direction=fusion_result.direction,
                entry_time=max(0, state.timestamp - 300000),
                exit_time=state.timestamp,
                entry_price=state.current_close,
                exit_price=state.current_close,
                pnl=synthetic_pnl,
                mae=0.35,
                mfe=0.90,
                exit_reason="phase_7_placeholder_close",
                contributing_signals=active_signals,
                regime=regime,
                size_tier=risk_decision.size_tier,
                notional_fraction=risk_decision.notional_fraction,
                metadata={
                    "note": "placeholder outcome until fully wired to Phase 6 trade lifecycle"
                },
            )
            ledger.record_outcome(outcome)

        processed += 1

        if processed % 5000 == 0:
            print(
                "[replay] Progress "
                f"processed={processed} timestamp={decision.timestamp} "
                f"regime={decision.market_regime} direction={decision.direction} "
                f"risk_budget={decision.risk_budget:.2f} "
                f"execution_allowed={decision.execution_allowed}"
            )

    summary = ledger.summary()
    scorecards = build_signal_scorecards(ledger.outcomes)

    print(f"[replay] Final summary metrics: {summary}")
    print(f"[replay] Final signal scorecards: {scorecards}")
    print("[replay] Phase 7 replay completed successfully")


if __name__ == "__main__":
    main()
EOF
```

---

# 9. Run Sequence

Run this after Phases 1 through 6 are already working:

```bash
python3 renaissance_v4/research/replay_runner.py
```

Phase 7 reuses the same Phase 1 dataset and the Phase 2–6 pipeline.

---

# 10. Expected Proof

Phase 7 is complete only when:

- replay still loads the dataset cleanly
- the prior pipeline still runs end-to-end
- completed trade outcomes are recorded
- portfolio-level summary metrics are printed
- per-signal scorecards are printed
- max drawdown is tracked
- lifecycle recommendations are generated
- the run completes without failure

---

# 11. What Comes After Phase 7

Only after this passes do we move to:

- promotion board
- decay detector
- signal state transitions
- walk-forward validation harness
- out-of-sample qualification gates

That will be Phase 8.

---

# 12. Final Statement

Phase 7 is where RenaissanceV4 begins remembering what happened.

Before this, it can behave.

After this, it can judge.

That is the first true step toward a system that learns which edges deserve to survive.
