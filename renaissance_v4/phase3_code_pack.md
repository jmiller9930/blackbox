# RenaissanceV4 — Phase 3 Code Pack
**System:** BlackBox  
**Authority:** Architect  
**Purpose:** Phase 3 implementation document for RenaissanceV4 signal architecture  
**Scope:** Signal base contract and the first four signal family modules  
**Status:** Build after Phase 2 passes

---

# 1. Objective

Phase 3 introduces the first real signal layer.

This phase still does **not** execute trades.

It defines:

- the canonical signal result contract
- the base signal interface
- the first four signal families
- replay integration so every bar can produce structured signal outputs

The goal is not to make money yet.

The goal is to prove that the system can generate **repeatable, explainable hypotheses** from the same market conditions every time.

---

# 2. What Phase 3 Includes

Phase 3 includes only:

1. `SignalResult` dataclass  
2. `BaseSignal` abstract class  
3. `TrendContinuationSignal`  
4. `PullbackContinuationSignal`  
5. `BreakoutExpansionSignal`  
6. `MeanReversionFadeSignal`  
7. replay runner integration for signal evaluation  
8. visible logging of signal outcomes  

Phase 3 does **not** include:

- fusion engine
- overlap penalties
- risk governor
- position sizing
- execution manager
- promotion board

Those come later.

---

# 3. Folder Structure Additions

```text
renaissance_v4/
├── core/
│   ├── decision_contract.py
│   ├── feature_set.py
│   ├── market_state.py
│   ├── feature_engine.py
│   ├── market_state_builder.py
│   └── regime_classifier.py
├── signals/
│   ├── signal_result.py
│   ├── base_signal.py
│   ├── trend_continuation.py
│   ├── pullback_continuation.py
│   ├── breakout_expansion.py
│   └── mean_reversion_fade.py
└── research/
    └── replay_runner.py
```

---

# 4. Build Order

Build in this exact order:

1. `signals/signal_result.py`
2. `signals/base_signal.py`
3. `signals/trend_continuation.py`
4. `signals/pullback_continuation.py`
5. `signals/breakout_expansion.py`
6. `signals/mean_reversion_fade.py`
7. update `research/replay_runner.py`

Do not start fusion or risk logic until this phase passes cleanly.

---

# 5. Phase 3 Design Rules

1. Signals are hypothesis generators only.
2. Signals never place trades.
3. Every signal must declare when it is inactive.
4. Every signal must emit a suppression reason when inactive.
5. Every signal must include an evidence trace with the main metrics that drove the decision.
6. Signal outputs must be deterministic for the same MarketState and FeatureSet.
7. Weak or mismatched conditions must resolve to neutral/inactive, not forced directional output.

---

# 6. Required Signal Output Contract

Every signal must return:

- `signal_name`
- `direction`
- `confidence`
- `expected_edge`
- `regime_fit`
- `stability_score`
- `active`
- `suppression_reason`
- `evidence_trace`

Allowed directions:

- `long`
- `short`
- `neutral`

---

# 7. Signal Families in Phase 3

## Trend Continuation
Purpose:
- express directional bias when market is already trending strongly

## Pullback Continuation
Purpose:
- express directional bias when market pulls back inside a trend but remains structurally intact

## Breakout Expansion
Purpose:
- express directional bias when compression appears to release into expansion

## Mean Reversion Fade
Purpose:
- express reversal bias when price looks stretched away from local mean in a non-trending environment

These signals are intentionally simple at first.

They exist to prove the architecture, not to optimize PnL yet.

---

# 8. CAT Blocks

## 8.1 Create `renaissance_v4/signals/signal_result.py`

```bash
cat > renaissance_v4/signals/signal_result.py << 'EOF'
"""
signal_result.py

Purpose:
Define the canonical SignalResult object for RenaissanceV4 signal modules.

Usage:
Returned by all signal classes and consumed by replay, fusion, and later risk logic.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SignalResult:
    """
    Canonical result object returned by each signal module.
    """
    signal_name: str
    direction: str
    confidence: float
    expected_edge: float
    regime_fit: float
    stability_score: float
    active: bool
    suppression_reason: str
    evidence_trace: dict[str, Any] = field(default_factory=dict)
EOF
```

---

## 8.2 Create `renaissance_v4/signals/base_signal.py`

```bash
cat > renaissance_v4/signals/base_signal.py << 'EOF'
"""
base_signal.py

Purpose:
Define the abstract base signal contract for all RenaissanceV4 signal modules.

Usage:
Inherited by all signal implementations to guarantee a common interface.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.signals.signal_result import SignalResult


class BaseSignal(ABC):
    """
    Abstract signal interface for all RenaissanceV4 signal modules.
    """

    signal_name: str = "base_signal"

    @abstractmethod
    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        """
        Evaluate the current market state and return a deterministic SignalResult.
        """
        raise NotImplementedError
EOF
```

---

## 8.3 Create `renaissance_v4/signals/trend_continuation.py`

```bash
cat > renaissance_v4/signals/trend_continuation.py << 'EOF'
"""
trend_continuation.py

Purpose:
Implement the TrendContinuationSignal for RenaissanceV4.

Usage:
Used during replay to express directional continuation bias in strong trend conditions.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.signals.base_signal import BaseSignal
from renaissance_v4.signals.signal_result import SignalResult

MIN_REGIME_FIT = 0.80
MIN_CONFIDENCE = 0.55


class TrendContinuationSignal(BaseSignal):
    """
    Express directional continuation when the trend regime is already established.
    """

    signal_name = "trend_continuation"

    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        direction = "neutral"
        confidence = 0.0
        expected_edge = 0.0
        regime_fit = 0.0
        stability_score = min(1.0, features.directional_persistence_10)
        active = False
        suppression_reason = ""

        if regime == "trend_up":
            regime_fit = 1.0
            if features.ema_distance > 0 and features.ema_slope > 0 and features.one_bar_return >= 0:
                direction = "long"
                confidence = min(1.0, 0.50 + abs(features.ema_slope) * 5 + features.directional_persistence_10 * 0.25)
                expected_edge = min(1.0, abs(features.ema_distance) / max(features.close_price, 1e-9))
        elif regime == "trend_down":
            regime_fit = 1.0
            if features.ema_distance < 0 and features.ema_slope < 0 and features.one_bar_return <= 0:
                direction = "short"
                confidence = min(1.0, 0.50 + abs(features.ema_slope) * 5 + features.directional_persistence_10 * 0.25)
                expected_edge = min(1.0, abs(features.ema_distance) / max(features.close_price, 1e-9))
        else:
            suppression_reason = f"regime_mismatch:{regime}"

        if direction == "neutral":
            if not suppression_reason:
                suppression_reason = "trend_conditions_not_met"
        else:
            active = regime_fit >= MIN_REGIME_FIT and confidence >= MIN_CONFIDENCE
            if not active:
                suppression_reason = "confidence_or_regime_fit_below_floor"

        result = SignalResult(
            signal_name=self.signal_name,
            direction=direction,
            confidence=confidence,
            expected_edge=expected_edge,
            regime_fit=regime_fit,
            stability_score=stability_score,
            active=active,
            suppression_reason=suppression_reason if not active else "",
            evidence_trace={
                "regime": regime,
                "ema_distance": features.ema_distance,
                "ema_slope": features.ema_slope,
                "one_bar_return": features.one_bar_return,
                "directional_persistence_10": features.directional_persistence_10,
            },
        )

        print(
            f"[signal:{self.signal_name}] direction={result.direction} "
            f"active={result.active} confidence={result.confidence:.4f} "
            f"reason={result.suppression_reason}"
        )

        return result
EOF
```

---

## 8.4 Create `renaissance_v4/signals/pullback_continuation.py`

```bash
cat > renaissance_v4/signals/pullback_continuation.py << 'EOF'
"""
pullback_continuation.py

Purpose:
Implement the PullbackContinuationSignal for RenaissanceV4.

Usage:
Used during replay to detect controlled retracement opportunities inside an active trend.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.signals.base_signal import BaseSignal
from renaissance_v4.signals.signal_result import SignalResult

MIN_CONFIDENCE = 0.52


class PullbackContinuationSignal(BaseSignal):
    """
    Express continuation after a controlled pullback inside a prevailing trend.
    """

    signal_name = "pullback_continuation"

    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        direction = "neutral"
        confidence = 0.0
        expected_edge = 0.0
        regime_fit = 0.0
        stability_score = min(1.0, 0.5 + features.directional_persistence_10 * 0.5)
        active = False
        suppression_reason = ""

        pulled_back = features.candle_body < max(features.candle_range * 0.60, 1e-9)
        not_explosive = features.volatility_20 < 0.02

        if regime == "trend_up":
            regime_fit = 0.90
            if features.ema_distance > 0 and features.one_bar_return <= 0 and pulled_back and not_explosive:
                direction = "long"
                confidence = min(1.0, 0.45 + features.directional_persistence_10 * 0.20 + abs(features.ema_distance) / max(features.close_price, 1e-9))
                expected_edge = min(1.0, abs(features.ema_distance) / max(features.close_price, 1e-9))
        elif regime == "trend_down":
            regime_fit = 0.90
            if features.ema_distance < 0 and features.one_bar_return >= 0 and pulled_back and not_explosive:
                direction = "short"
                confidence = min(1.0, 0.45 + features.directional_persistence_10 * 0.20 + abs(features.ema_distance) / max(features.close_price, 1e-9))
                expected_edge = min(1.0, abs(features.ema_distance) / max(features.close_price, 1e-9))
        else:
            suppression_reason = f"regime_mismatch:{regime}"

        if direction == "neutral":
            if not suppression_reason:
                suppression_reason = "pullback_conditions_not_met"
        else:
            active = confidence >= MIN_CONFIDENCE
            if not active:
                suppression_reason = "confidence_below_floor"

        result = SignalResult(
            signal_name=self.signal_name,
            direction=direction,
            confidence=confidence,
            expected_edge=expected_edge,
            regime_fit=regime_fit,
            stability_score=stability_score,
            active=active,
            suppression_reason=suppression_reason if not active else "",
            evidence_trace={
                "regime": regime,
                "ema_distance": features.ema_distance,
                "one_bar_return": features.one_bar_return,
                "candle_body": features.candle_body,
                "candle_range": features.candle_range,
                "volatility_20": features.volatility_20,
            },
        )

        print(
            f"[signal:{self.signal_name}] direction={result.direction} "
            f"active={result.active} confidence={result.confidence:.4f} "
            f"reason={result.suppression_reason}"
        )

        return result
EOF
```

---

## 8.5 Create `renaissance_v4/signals/breakout_expansion.py`

```bash
cat > renaissance_v4/signals/breakout_expansion.py << 'EOF'
"""
breakout_expansion.py

Purpose:
Implement the BreakoutExpansionSignal for RenaissanceV4.

Usage:
Used during replay to detect expansion after relatively compressed conditions.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.signals.base_signal import BaseSignal
from renaissance_v4.signals.signal_result import SignalResult

MIN_CONFIDENCE = 0.56


class BreakoutExpansionSignal(BaseSignal):
    """
    Express breakout bias after compression begins to release.
    """

    signal_name = "breakout_expansion"

    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        direction = "neutral"
        confidence = 0.0
        expected_edge = 0.0
        regime_fit = 0.0
        stability_score = 0.70
        active = False
        suppression_reason = ""

        avg_close = max(features.avg_close_20, 1e-9)
        large_bar = features.candle_range / avg_close > 0.004

        if regime == "volatility_expansion":
            regime_fit = 1.0
            if features.one_bar_return > 0 and large_bar and features.ema_slope >= 0:
                direction = "long"
                confidence = min(1.0, 0.50 + features.volatility_20 * 10 + features.compression_ratio * 20)
                expected_edge = min(1.0, features.candle_range / avg_close)
            elif features.one_bar_return < 0 and large_bar and features.ema_slope <= 0:
                direction = "short"
                confidence = min(1.0, 0.50 + features.volatility_20 * 10 + features.compression_ratio * 20)
                expected_edge = min(1.0, features.candle_range / avg_close)
            else:
                suppression_reason = "expansion_detected_but_direction_unclear"
        else:
            suppression_reason = f"regime_mismatch:{regime}"

        if direction != "neutral":
            active = confidence >= MIN_CONFIDENCE
            if not active:
                suppression_reason = "confidence_below_floor"

        result = SignalResult(
            signal_name=self.signal_name,
            direction=direction,
            confidence=confidence,
            expected_edge=expected_edge,
            regime_fit=regime_fit,
            stability_score=stability_score,
            active=active,
            suppression_reason=suppression_reason if not active else "",
            evidence_trace={
                "regime": regime,
                "one_bar_return": features.one_bar_return,
                "candle_range": features.candle_range,
                "avg_close_20": features.avg_close_20,
                "volatility_20": features.volatility_20,
                "compression_ratio": features.compression_ratio,
                "ema_slope": features.ema_slope,
            },
        )

        print(
            f"[signal:{self.signal_name}] direction={result.direction} "
            f"active={result.active} confidence={result.confidence:.4f} "
            f"reason={result.suppression_reason}"
        )

        return result
EOF
```

---

## 8.6 Create `renaissance_v4/signals/mean_reversion_fade.py`

```bash
cat > renaissance_v4/signals/mean_reversion_fade.py << 'EOF'
"""
mean_reversion_fade.py

Purpose:
Implement the MeanReversionFadeSignal for RenaissanceV4.

Usage:
Used during replay to express fade bias when price appears stretched in non-trending conditions.

Version:
v1.0

Change History:
- v1.0 Initial Phase 3 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.signals.base_signal import BaseSignal
from renaissance_v4.signals.signal_result import SignalResult

MIN_CONFIDENCE = 0.53


class MeanReversionFadeSignal(BaseSignal):
    """
    Express reversal bias away from local stretch in range or compressed environments.
    """

    signal_name = "mean_reversion_fade"

    def evaluate(self, state: MarketState, features: FeatureSet, regime: str) -> SignalResult:
        direction = "neutral"
        confidence = 0.0
        expected_edge = 0.0
        regime_fit = 0.0
        stability_score = 0.65
        active = False
        suppression_reason = ""

        deviation_from_mean = 0.0
        if features.avg_close_20 != 0:
            deviation_from_mean = (features.close_price - features.avg_close_20) / features.avg_close_20

        range_like_regime = regime in {"range", "volatility_compression"}

        if range_like_regime:
            regime_fit = 0.90
            if deviation_from_mean > 0.003 and features.one_bar_return >= 0:
                direction = "short"
                confidence = min(1.0, 0.45 + abs(deviation_from_mean) * 40)
                expected_edge = min(1.0, abs(deviation_from_mean) * 10)
            elif deviation_from_mean < -0.003 and features.one_bar_return <= 0:
                direction = "long"
                confidence = min(1.0, 0.45 + abs(deviation_from_mean) * 40)
                expected_edge = min(1.0, abs(deviation_from_mean) * 10)
            else:
                suppression_reason = "stretch_threshold_not_met"
        else:
            suppression_reason = f"regime_mismatch:{regime}"

        if direction != "neutral":
            active = confidence >= MIN_CONFIDENCE
            if not active:
                suppression_reason = "confidence_below_floor"

        result = SignalResult(
            signal_name=self.signal_name,
            direction=direction,
            confidence=confidence,
            expected_edge=expected_edge,
            regime_fit=regime_fit,
            stability_score=stability_score,
            active=active,
            suppression_reason=suppression_reason if not active else "",
            evidence_trace={
                "regime": regime,
                "close_price": features.close_price,
                "avg_close_20": features.avg_close_20,
                "deviation_from_mean": deviation_from_mean,
                "one_bar_return": features.one_bar_return,
            },
        )

        print(
            f"[signal:{self.signal_name}] direction={result.direction} "
            f"active={result.active} confidence={result.confidence:.4f} "
            f"reason={result.suppression_reason}"
        )

        return result
EOF
```

---

## 8.7 Update `renaissance_v4/research/replay_runner.py`

```bash
cat > renaissance_v4/research/replay_runner.py << 'EOF'
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
EOF
```

---

# 9. Run Sequence

Run this after Phases 1 and 2 are already working:

```bash
python3 renaissance_v4/research/replay_runner.py
```

Phase 3 reuses the same Phase 1 database and the Phase 2 market interpretation pipeline.

---

# 10. Expected Proof

Phase 3 is complete only when:

- replay still loads the dataset cleanly
- MarketState and FeatureSet continue to build correctly
- every eligible replay step produces a regime
- every eligible replay step evaluates all four signals
- logs clearly show which signals were active and which were suppressed
- the run completes end-to-end without failure

---

# 11. What Comes After Phase 3

Only after this passes do we move to:

- fusion engine
- signal conflict handling
- weighted evidence scoring
- overlap penalties
- no-trade decision threshold

That will be Phase 4.

---

# 12. Final Statement

Phase 3 is where RenaissanceV4 starts forming opinions.

They are not yet capitalized.

They are not yet fused.

But the machine is no longer just observing the market.

It is now generating structured hypotheses that later phases can judge.
