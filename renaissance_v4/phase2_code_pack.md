# RenaissanceV4 — Phase 2 Code Pack
**System:** BlackBox  
**Authority:** Architect  
**Purpose:** Phase 2 implementation document for RenaissanceV4 core market interpretation  
**Scope:** MarketState builder, feature engine, and regime classifier  
**Status:** Build after Phase 1 passes

---

# 1. Objective

Phase 2 turns the Phase 1 replay shell into the first real analytical pipeline.

This phase still does **not** place trades.

It adds the first layer of market understanding so later signal modules can operate on structured, reproducible inputs.

Phase 2 builds:

- a MarketState object
- a FeatureSet object
- a regime classifier
- replay integration for these components

If Phase 2 is weak, all later signals become subjective and inconsistent.

---

# 2. What Phase 2 Includes

Phase 2 includes only:

1. MarketState dataclass  
2. FeatureSet dataclass  
3. MarketState builder  
4. Feature engine  
5. Regime classifier  
6. Replay runner integration  
7. screen-visible debug output  

Phase 2 does **not** include:

- real signal modules
- fusion engine
- risk governor
- execution logic
- paper trading logic

---

# 3. Folder Structure Additions

```text
renaissance_v4/
├── core/
│   ├── decision_contract.py
│   ├── market_state.py
│   ├── feature_set.py
│   ├── market_state_builder.py
│   ├── feature_engine.py
│   └── regime_classifier.py
├── research/
│   └── replay_runner.py
└── utils/
    └── math_utils.py
```

---

# 4. Build Order

Build in this exact order:

1. `utils/math_utils.py`
2. `core/market_state.py`
3. `core/feature_set.py`
4. `core/market_state_builder.py`
5. `core/feature_engine.py`
6. `core/regime_classifier.py`
7. update `research/replay_runner.py`

Do not start signal coding before this passes.

---

# 5. Phase 2 Design Rules

1. The builder must only use bars that would have been known at that point in time.
2. The feature engine must be deterministic and reproducible.
3. The regime classifier must stay simple and explicit.
4. Unknown or weak conditions must classify as `unstable`.
5. Every step must print enough information to diagnose failures quickly.
6. No hidden magic numbers inside random functions; use named constants.

---

# 6. Feature Targets for Phase 2

The initial feature engine will calculate:

- close price
- high-low range
- candle body size
- upper wick size
- lower wick size
- simple return from previous close
- rolling average close
- rolling average volume
- EMA fast
- EMA slow
- EMA distance
- EMA slope
- rolling volatility proxy
- directional persistence
- ATR proxy
- compression ratio

This is enough to support the first regime pass.

---

# 7. Regime Labels for Phase 2

Phase 2 regime output must be one of:

- `trend_up`
- `trend_down`
- `range`
- `volatility_expansion`
- `volatility_compression`
- `unstable`

If the classifier is not confident, return `unstable`.

---

# 8. CAT Blocks

## 8.1 Create `renaissance_v4/utils/math_utils.py`

```bash
cat > renaissance_v4/utils/math_utils.py << 'EOF'
"""
math_utils.py

Purpose:
Provide reusable deterministic math helpers for RenaissanceV4 feature calculations.

Usage:
Imported by the feature engine and regime classifier.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from typing import Iterable


def safe_mean(values: Iterable[float]) -> float:
    """
    Return the arithmetic mean of the provided values.
    Returns 0.0 when the iterable is empty.
    """
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def safe_stddev(values: Iterable[float]) -> float:
    """
    Return a simple population standard deviation.
    Returns 0.0 when the iterable has fewer than 2 items.
    """
    items = list(values)
    if len(items) < 2:
        return 0.0
    mean_value = safe_mean(items)
    variance = sum((item - mean_value) ** 2 for item in items) / len(items)
    return variance ** 0.5


def ema(values: list[float], period: int) -> float:
    """
    Compute a simple exponential moving average for the provided list.
    Uses the full input list and returns the last EMA value.
    Returns 0.0 when there is no data.
    """
    if not values:
        return 0.0

    multiplier = 2 / (period + 1)
    ema_value = values[0]

    for value in values[1:]:
        ema_value = ((value - ema_value) * multiplier) + ema_value

    return ema_value
EOF
```

---

## 8.2 Create `renaissance_v4/core/market_state.py`

```bash
cat > renaissance_v4/core/market_state.py << 'EOF'
"""
market_state.py

Purpose:
Define the canonical MarketState object for one replay step.

Usage:
Produced by the market state builder and consumed by the feature engine.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketState:
    """
    Represents the currently known historical market window at one replay step.
    """
    symbol: str
    timestamp: int
    closes: list[float]
    highs: list[float]
    lows: list[float]
    opens: list[float]
    volumes: list[float]
    current_open: float
    current_high: float
    current_low: float
    current_close: float
    current_volume: float
EOF
```

---

## 8.3 Create `renaissance_v4/core/feature_set.py`

```bash
cat > renaissance_v4/core/feature_set.py << 'EOF'
"""
feature_set.py

Purpose:
Define the canonical FeatureSet object for one replay step.

Usage:
Produced by the feature engine and consumed by the regime classifier and future signals.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FeatureSet:
    """
    Holds deterministic features derived from the current MarketState.
    """
    close_price: float
    candle_range: float
    candle_body: float
    upper_wick: float
    lower_wick: float
    one_bar_return: float
    avg_close_20: float
    avg_volume_20: float
    ema_fast_10: float
    ema_slow_20: float
    ema_distance: float
    ema_slope: float
    volatility_20: float
    directional_persistence_10: float
    atr_proxy_14: float
    compression_ratio: float
EOF
```

---

## 8.4 Create `renaissance_v4/core/market_state_builder.py`

```bash
cat > renaissance_v4/core/market_state_builder.py << 'EOF'
"""
market_state_builder.py

Purpose:
Build a MarketState object from a rolling historical bar window.

Usage:
Used by the replay runner before feature generation.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.market_state import MarketState

WINDOW_SIZE = 50


def build_market_state(rows: list) -> MarketState:
    """
    Build and return a MarketState from a list of SQLite rows.
    The final row in the list is treated as the current bar.
    """
    if not rows:
        raise ValueError("[market_state_builder] No rows provided")

    window = rows[-WINDOW_SIZE:]
    current_row = window[-1]

    closes = [float(row["close"]) for row in window]
    highs = [float(row["high"]) for row in window]
    lows = [float(row["low"]) for row in window]
    opens = [float(row["open"]) for row in window]
    volumes = [float(row["volume"]) for row in window]

    state = MarketState(
        symbol=current_row["symbol"],
        timestamp=int(current_row["open_time"]),
        closes=closes,
        highs=highs,
        lows=lows,
        opens=opens,
        volumes=volumes,
        current_open=float(current_row["open"]),
        current_high=float(current_row["high"]),
        current_low=float(current_row["low"]),
        current_close=float(current_row["close"]),
        current_volume=float(current_row["volume"]),
    )

    print(
        "[market_state_builder] Built MarketState "
        f"symbol={state.symbol} timestamp={state.timestamp} close={state.current_close}"
    )

    return state
EOF
```

---

## 8.5 Create `renaissance_v4/core/feature_engine.py`

```bash
cat > renaissance_v4/core/feature_engine.py << 'EOF'
"""
feature_engine.py

Purpose:
Convert MarketState into a deterministic FeatureSet for RenaissanceV4.

Usage:
Used by the replay runner after the MarketState builder.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.market_state import MarketState
from renaissance_v4.utils.math_utils import ema, safe_mean, safe_stddev

FAST_EMA_PERIOD = 10
SLOW_EMA_PERIOD = 20
VOL_WINDOW = 20
ATR_WINDOW = 14
PERSISTENCE_WINDOW = 10


def build_feature_set(state: MarketState) -> FeatureSet:
    """
    Build a deterministic FeatureSet from the current MarketState.
    Prints a compact feature summary for visible debugging.
    """
    candle_range = state.current_high - state.current_low
    candle_body = abs(state.current_close - state.current_open)
    upper_wick = state.current_high - max(state.current_open, state.current_close)
    lower_wick = min(state.current_open, state.current_close) - state.current_low

    one_bar_return = 0.0
    if len(state.closes) >= 2 and state.closes[-2] != 0:
        one_bar_return = (state.closes[-1] - state.closes[-2]) / state.closes[-2]

    avg_close_20 = safe_mean(state.closes[-20:])
    avg_volume_20 = safe_mean(state.volumes[-20:])

    ema_fast_10 = ema(state.closes[-FAST_EMA_PERIOD * 3 :], FAST_EMA_PERIOD)
    ema_slow_20 = ema(state.closes[-SLOW_EMA_PERIOD * 3 :], SLOW_EMA_PERIOD)
    ema_distance = ema_fast_10 - ema_slow_20

    prior_ema_fast = ema(state.closes[-(FAST_EMA_PERIOD * 3 + 1) : -1], FAST_EMA_PERIOD)
    ema_slope = ema_fast_10 - prior_ema_fast

    close_returns = []
    for index in range(1, len(state.closes[-VOL_WINDOW:])):
        previous_close = state.closes[-VOL_WINDOW:][index - 1]
        current_close = state.closes[-VOL_WINDOW:][index]
        if previous_close != 0:
            close_returns.append((current_close - previous_close) / previous_close)

    volatility_20 = safe_stddev(close_returns)

    recent_direction_flags = []
    close_slice = state.closes[-PERSISTENCE_WINDOW:]
    for index in range(1, len(close_slice)):
        if close_slice[index] > close_slice[index - 1]:
            recent_direction_flags.append(1.0)
        elif close_slice[index] < close_slice[index - 1]:
            recent_direction_flags.append(-1.0)
        else:
            recent_direction_flags.append(0.0)

    directional_persistence_10 = abs(safe_mean(recent_direction_flags))

    true_ranges = []
    lookback_highs = state.highs[-ATR_WINDOW:]
    lookback_lows = state.lows[-ATR_WINDOW:]
    lookback_closes = state.closes[-(ATR_WINDOW + 1):]

    for index in range(len(lookback_highs)):
        high_value = lookback_highs[index]
        low_value = lookback_lows[index]
        previous_close = lookback_closes[index]
        true_range = max(
            high_value - low_value,
            abs(high_value - previous_close),
            abs(low_value - previous_close),
        )
        true_ranges.append(true_range)

    atr_proxy_14 = safe_mean(true_ranges)
    compression_ratio = 0.0
    if avg_close_20 != 0:
        compression_ratio = candle_range / avg_close_20

    feature_set = FeatureSet(
        close_price=state.current_close,
        candle_range=candle_range,
        candle_body=candle_body,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        one_bar_return=one_bar_return,
        avg_close_20=avg_close_20,
        avg_volume_20=avg_volume_20,
        ema_fast_10=ema_fast_10,
        ema_slow_20=ema_slow_20,
        ema_distance=ema_distance,
        ema_slope=ema_slope,
        volatility_20=volatility_20,
        directional_persistence_10=directional_persistence_10,
        atr_proxy_14=atr_proxy_14,
        compression_ratio=compression_ratio,
    )

    print(
        "[feature_engine] Features "
        f"close={feature_set.close_price:.4f} "
        f"ema_distance={feature_set.ema_distance:.4f} "
        f"ema_slope={feature_set.ema_slope:.4f} "
        f"volatility_20={feature_set.volatility_20:.6f} "
        f"persistence={feature_set.directional_persistence_10:.4f}"
    )

    return feature_set
EOF
```

---

## 8.6 Create `renaissance_v4/core/regime_classifier.py`

```bash
cat > renaissance_v4/core/regime_classifier.py << 'EOF'
"""
regime_classifier.py

Purpose:
Classify the current market regime from deterministic Phase 2 features.

Usage:
Used by the replay runner after feature generation.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet

TREND_DISTANCE_THRESHOLD = 0.15
TREND_SLOPE_THRESHOLD = 0.02
PERSISTENCE_THRESHOLD = 0.60
VOLATILITY_EXPANSION_THRESHOLD = 0.008
VOLATILITY_COMPRESSION_THRESHOLD = 0.0025
COMPRESSION_RATIO_LOW = 0.0015
COMPRESSION_RATIO_HIGH = 0.008


def classify_regime(features: FeatureSet) -> str:
    """
    Classify the current market state into one of the Phase 2 regime buckets.
    Prints the chosen regime for visible debugging.
    """
    regime = "unstable"

    if (
        features.ema_distance > TREND_DISTANCE_THRESHOLD
        and features.ema_slope > TREND_SLOPE_THRESHOLD
        and features.directional_persistence_10 >= PERSISTENCE_THRESHOLD
    ):
        regime = "trend_up"
    elif (
        features.ema_distance < -TREND_DISTANCE_THRESHOLD
        and features.ema_slope < -TREND_SLOPE_THRESHOLD
        and features.directional_persistence_10 >= PERSISTENCE_THRESHOLD
    ):
        regime = "trend_down"
    elif (
        features.volatility_20 >= VOLATILITY_EXPANSION_THRESHOLD
        and features.compression_ratio >= COMPRESSION_RATIO_HIGH
    ):
        regime = "volatility_expansion"
    elif (
        features.volatility_20 <= VOLATILITY_COMPRESSION_THRESHOLD
        and features.compression_ratio <= COMPRESSION_RATIO_LOW
    ):
        regime = "volatility_compression"
    elif abs(features.ema_distance) < TREND_DISTANCE_THRESHOLD and features.directional_persistence_10 < PERSISTENCE_THRESHOLD:
        regime = "range"

    print(f"[regime_classifier] Regime classified as: {regime}")
    return regime
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
Run directly after Phase 1 and Phase 2 files are installed to validate the market-state and feature pipeline.

Version:
v2.0

Change History:
- v1.0 Initial Phase 1 replay shell.
- v2.0 Added MarketState builder, feature engine, and regime classifier integration.
"""

from __future__ import annotations

import uuid

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.regime_classifier import classify_regime
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50


def main() -> None:
    """
    Iterate through historical bars in strict chronological order.
    Builds MarketState, FeatureSet, and regime output for each eligible replay step.
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

    processed = 0

    for index in range(MIN_ROWS_REQUIRED, len(rows) + 1):
        window = rows[:index]
        state = build_market_state(window)
        features = build_feature_set(state)
        regime = classify_regime(features)

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
                "phase": "phase_2_market_interpretation",
                "regime": regime,
                "close": features.close_price,
                "ema_distance": features.ema_distance,
                "ema_slope": features.ema_slope,
                "volatility_20": features.volatility_20,
                "directional_persistence_10": features.directional_persistence_10,
            },
        )

        processed += 1

        if processed % 5000 == 0:
            print(
                "[replay] Progress "
                f"processed={processed} "
                f"timestamp={decision.timestamp} "
                f"regime={decision.market_regime} "
                f"direction={decision.direction}"
            )

    print("[replay] Phase 2 replay completed successfully")


if __name__ == "__main__":
    main()
EOF
```

---

# 9. Run Sequence

Run these commands in order after Phase 1 is already working:

```bash
python3 renaissance_v4/research/replay_runner.py
```

Phase 2 reuses the Phase 1 database and historical dataset.

---

# 10. Expected Proof

Phase 2 is complete only when:

- replay still loads the dataset cleanly
- MarketState objects build successfully
- FeatureSet objects calculate without error
- every eligible replay step produces a regime
- the run finishes end-to-end
- logs clearly show feature and regime output

---

# 11. What Comes After Phase 2

Only after this passes do we move to:

- signal base class
- trend continuation signal
- pullback continuation signal
- breakout expansion signal
- mean reversion fade signal

That will be Phase 3.

---

# 12. Final Statement

Phase 2 is where RenaissanceV4 begins to understand the market in a structured way.

It still does not trade.

But it stops being blind.

That is the requirement before signals are allowed to exist.
