# RenaissanceV4 — Phase 4 Code Pack
**System:** BlackBox  
**Authority:** Architect  
**Purpose:** Phase 4 implementation document for RenaissanceV4 evidence fusion and no-trade decisioning  
**Scope:** Fusion engine, signal weighting, conflict handling, overlap penalties, and decision threshold logic  
**Status:** Build after Phase 3 passes

---

# 1. Objective

Phase 4 is where RenaissanceV4 stops being a collection of isolated signal opinions and begins acting like a governed decision system.

This phase still does **not** size risk or execute trades.

It adds:

- a canonical fusion result contract
- weighted evidence scoring
- signal lifecycle weighting hooks
- conflict penalties
- overlap penalties
- no-trade threshold logic
- replay integration for final directional decision output

The goal is to prove that multiple signal hypotheses can be combined into one disciplined decision without forcing activity.

---

# 2. What Phase 4 Includes

Phase 4 includes only:

1. `FusionResult` dataclass  
2. `signal_weights.py` helper  
3. `fusion_engine.py`  
4. conflict scoring  
5. overlap penalties  
6. no-trade threshold logic  
7. replay runner integration for fused decision output  
8. visible logging of final fused decisions  

Phase 4 does **not** include:

- risk governor
- position sizing
- execution manager
- trade simulation
- promotion board
- decay detector

Those come later.

---

# 3. Folder Structure Additions

```text
renaissance_v4/
├── core/
│   ├── decision_contract.py
│   ├── feature_engine.py
│   ├── feature_set.py
│   ├── fusion_engine.py
│   ├── fusion_result.py
│   ├── market_state.py
│   ├── market_state_builder.py
│   ├── regime_classifier.py
│   └── signal_weights.py
├── signals/
│   ├── base_signal.py
│   ├── breakout_expansion.py
│   ├── mean_reversion_fade.py
│   ├── pullback_continuation.py
│   ├── signal_result.py
│   └── trend_continuation.py
└── research/
    └── replay_runner.py
```

---

# 4. Build Order

Build in this exact order:

1. `core/fusion_result.py`
2. `core/signal_weights.py`
3. `core/fusion_engine.py`
4. update `research/replay_runner.py`

Do not start risk or execution work until this phase passes cleanly.

---

# 5. Phase 4 Design Rules

1. Fusion must prefer `no_trade` over weak evidence.
2. Active signals are weighted; suppressed signals do not vote.
3. Different signals are not treated equally by default.
4. If long and short evidence conflict too strongly, return `no_trade`.
5. If too many signals are effectively saying the same thing, apply overlap penalties.
6. Every fused decision must be explainable from logs and traces.
7. Thresholds must be named constants, not hidden magic values.
8. Phase 4 produces direction only, not capital allocation.

---

# 6. Fusion Model for Phase 4

Each active signal contributes to a directional evidence pool.

The fusion engine must compute:

- total long evidence
- total short evidence
- gross evidence
- conflict score
- overlap penalty
- winning direction
- final fusion score
- threshold pass/fail

The fusion engine must then output one of:

- `long`
- `short`
- `no_trade`

If evidence is weak, conflicted, or over-duplicated:
- output `no_trade`

---

# 7. Lifecycle Weight Hook

Phase 4 introduces a placeholder lifecycle weighting layer so later phases can scale signal influence without changing fusion design.

For now, use fixed default weights:

- `trend_continuation` → 1.00
- `pullback_continuation` → 0.90
- `breakout_expansion` → 0.95
- `mean_reversion_fade` → 0.85

This is not promotion logic yet.
It is only a stable weighting baseline.

---

# 8. CAT Blocks

## 8.1 Create `renaissance_v4/core/fusion_result.py`

```bash
cat > renaissance_v4/core/fusion_result.py << 'EOF'
"""
fusion_result.py

Purpose:
Define the canonical FusionResult object for RenaissanceV4 evidence fusion.

Usage:
Produced by the fusion engine and consumed by replay, risk, and later execution logic.

Version:
v1.0

Change History:
- v1.0 Initial Phase 4 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FusionResult:
    """
    Canonical output object for evidence fusion across signal modules.
    """
    direction: str
    fusion_score: float
    long_score: float
    short_score: float
    gross_score: float
    conflict_score: float
    overlap_penalty: float
    threshold_passed: bool
    contributing_signals: list[str] = field(default_factory=list)
    suppressed_signals: list[str] = field(default_factory=list)
    debug_trace: dict[str, Any] = field(default_factory=dict)
EOF
```

---

## 8.2 Create `renaissance_v4/core/signal_weights.py`

```bash
cat > renaissance_v4/core/signal_weights.py << 'EOF'
"""
signal_weights.py

Purpose:
Provide stable default signal weights for RenaissanceV4 Phase 4 fusion.

Usage:
Imported by the fusion engine to weight active signals consistently.

Version:
v1.0

Change History:
- v1.0 Initial Phase 4 implementation.
"""

from __future__ import annotations

DEFAULT_SIGNAL_WEIGHTS = {
    "trend_continuation": 1.00,
    "pullback_continuation": 0.90,
    "breakout_expansion": 0.95,
    "mean_reversion_fade": 0.85,
}


def get_signal_weight(signal_name: str) -> float:
    """
    Return the configured default weight for a signal.
    Falls back to 1.0 if the signal name is unknown.
    """
    return DEFAULT_SIGNAL_WEIGHTS.get(signal_name, 1.0)
EOF
```

---

## 8.3 Create `renaissance_v4/core/fusion_engine.py`

```bash
cat > renaissance_v4/core/fusion_engine.py << 'EOF'
"""
fusion_engine.py

Purpose:
Fuse active signal outputs into one directional decision for RenaissanceV4.

Usage:
Used by the replay runner after all signal modules have been evaluated.

Version:
v1.0

Change History:
- v1.0 Initial Phase 4 implementation.
"""

from __future__ import annotations

from collections import Counter

from renaissance_v4.core.fusion_result import FusionResult
from renaissance_v4.core.signal_weights import get_signal_weight
from renaissance_v4.signals.signal_result import SignalResult

MIN_FUSION_SCORE = 0.55
MAX_CONFLICT_SCORE = 0.45
MAX_OVERLAP_BUCKET_COUNT = 2
OVERLAP_PENALTY_PER_EXTRA_SIGNAL = 0.08


def _directional_contribution(signal: SignalResult) -> float:
    """
    Convert a signal result into a weighted directional contribution before overlap adjustments.
    """
    if not signal.active or signal.direction not in {"long", "short"}:
        return 0.0

    base_weight = get_signal_weight(signal.signal_name)
    contribution = (
        signal.confidence
        * max(signal.expected_edge, 0.0)
        * max(signal.regime_fit, 0.0)
        * max(signal.stability_score, 0.0)
        * base_weight
    )
    return contribution


def _signal_bucket(signal_name: str) -> str:
    """
    Collapse signal names into coarse buckets so similar hypotheses can be overlap-penalized.
    """
    if signal_name in {"trend_continuation", "pullback_continuation"}:
        return "trend_family"
    if signal_name == "breakout_expansion":
        return "breakout_family"
    if signal_name == "mean_reversion_fade":
        return "mean_reversion_family"
    return "other"


def fuse_signal_results(signal_results: list[SignalResult]) -> FusionResult:
    """
    Fuse active signal results into one directional output.
    Prefers no_trade whenever evidence is weak, conflicted, or overly redundant.
    """
    long_score = 0.0
    short_score = 0.0
    contributing_signals: list[str] = []
    suppressed_signals: list[str] = []
    active_buckets: list[str] = []

    for result in signal_results:
        if result.active and result.direction in {"long", "short"}:
            contribution = _directional_contribution(result)
            contributing_signals.append(f"{result.signal_name}:{result.direction}:{contribution:.4f}")
            active_buckets.append(_signal_bucket(result.signal_name))

            if result.direction == "long":
                long_score += contribution
            elif result.direction == "short":
                short_score += contribution
        else:
            suppressed_signals.append(f"{result.signal_name}:{result.suppression_reason}")

    gross_score = long_score + short_score

    conflict_score = 0.0
    if gross_score > 0:
        conflict_score = min(long_score, short_score) / gross_score

    bucket_counts = Counter(active_buckets)
    overlap_penalty = 0.0
    for bucket_name, count in bucket_counts.items():
        if count > MAX_OVERLAP_BUCKET_COUNT:
            extra = count - MAX_OVERLAP_BUCKET_COUNT
            penalty = extra * OVERLAP_PENALTY_PER_EXTRA_SIGNAL
            overlap_penalty += penalty
            print(
                f"[fusion_engine] Overlap penalty applied bucket={bucket_name} "
                f"count={count} penalty={penalty:.4f}"
            )

    raw_winning_score = max(long_score, short_score)
    fusion_score = max(0.0, raw_winning_score - overlap_penalty)

    direction = "no_trade"
    threshold_passed = False

    if gross_score == 0:
        direction = "no_trade"
    elif conflict_score > MAX_CONFLICT_SCORE:
        direction = "no_trade"
    elif fusion_score >= MIN_FUSION_SCORE:
        direction = "long" if long_score > short_score else "short"
        threshold_passed = True
    else:
        direction = "no_trade"

    result = FusionResult(
        direction=direction,
        fusion_score=fusion_score,
        long_score=long_score,
        short_score=short_score,
        gross_score=gross_score,
        conflict_score=conflict_score,
        overlap_penalty=overlap_penalty,
        threshold_passed=threshold_passed,
        contributing_signals=contributing_signals,
        suppressed_signals=suppressed_signals,
        debug_trace={
            "min_fusion_score": MIN_FUSION_SCORE,
            "max_conflict_score": MAX_CONFLICT_SCORE,
            "bucket_counts": dict(bucket_counts),
        },
    )

    print(
        "[fusion_engine] Fused decision "
        f"direction={result.direction} fusion_score={result.fusion_score:.4f} "
        f"long_score={result.long_score:.4f} short_score={result.short_score:.4f} "
        f"conflict_score={result.conflict_score:.4f} overlap_penalty={result.overlap_penalty:.4f}"
    )

    return result
EOF
```

---

## 8.4 Update `renaissance_v4/research/replay_runner.py`

```bash
cat > renaissance_v4/research/replay_runner.py << 'EOF'
"""
replay_runner.py

Purpose:
Run a deterministic bar-by-bar replay over historical 5-minute bars.

Usage:
Run directly after Phases 1 through 4 are installed to validate market-state, feature, regime, signal, and fusion logic.

Version:
v4.0

Change History:
- v1.0 Initial Phase 1 replay shell.
- v2.0 Added MarketState builder, feature engine, and regime classifier integration.
- v3.0 Added signal evaluation layer integration.
- v4.0 Added fusion engine integration and no-trade threshold logic.
"""

from __future__ import annotations

import uuid

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.fusion_engine import fuse_signal_results
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
    Build MarketState, FeatureSet, regime, signal outputs, and final fused decision.
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
        for signal in signals:
            result = signal.evaluate(state, features, regime)
            signal_results.append(result)

        fusion_result = fuse_signal_results(signal_results)

        confidence_score = fusion_result.fusion_score
        edge_score = max(fusion_result.long_score, fusion_result.short_score)

        decision = DecisionContract(
            decision_id=str(uuid.uuid4()),
            symbol=state.symbol,
            timestamp=state.timestamp,
            market_regime=regime,
            direction=fusion_result.direction,
            fusion_score=fusion_result.fusion_score,
            confidence_score=confidence_score,
            edge_score=edge_score,
            risk_budget=0.0,
            execution_allowed=False,
            reason_trace={
                "phase": "phase_4_fusion_logic",
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
                f"fusion_score={decision.fusion_score:.4f}"
            )

    print("[replay] Phase 4 replay completed successfully")


if __name__ == "__main__":
    main()
EOF
```

---

# 9. Run Sequence

Run this after Phases 1, 2, and 3 are already working:

```bash
python3 renaissance_v4/research/replay_runner.py
```

Phase 4 reuses the same Phase 1 dataset and the Phase 2–3 interpretation pipeline.

---

# 10. Expected Proof

Phase 4 is complete only when:

- replay still loads the dataset cleanly
- MarketState, FeatureSet, and regime output continue to work
- all four signals continue to evaluate per bar
- every eligible replay step produces a fused directional decision
- weak/conflicted setups resolve to `no_trade`
- logs clearly show fusion score, conflict score, and overlap penalty
- the run completes end-to-end without failure

---

# 11. What Comes After Phase 4

Only after this passes do we move to:

- risk governor
- size tiers
- allocation compression
- execution_allowed logic
- risk veto reasons

That will be Phase 5.

---

# 12. Final Statement

Phase 4 is where RenaissanceV4 stops merely generating opinions and starts making governed directional judgments.

It still does not allocate capital.

But it now knows how to say:

- `long`
- `short`
- `no_trade`

with explicit reasons.

That is the requirement before risk is allowed to enter the system.
