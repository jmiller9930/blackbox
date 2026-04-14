# RenaissanceV4 — Phase 5 Code Pack
**System:** BlackBox  
**Authority:** Architect  
**Purpose:** Phase 5 implementation document for RenaissanceV4 risk governance and execution gating  
**Scope:** Risk governor, size tiers, allocation compression, risk veto reasons, and replay integration  
**Status:** Build after Phase 4 passes

---

# 1. Objective

Phase 5 is where RenaissanceV4 earns the right to control capital exposure.

This phase still does **not** place real trades.

It adds the layer that stands between directional opinion and allowed action.

Phase 5 builds:

- a canonical risk decision contract
- size tiers
- allocation compression logic
- risk veto reasons
- execution gating
- replay integration so every fused decision is either allowed, reduced, probed, or blocked

The goal is to prove that even a valid directional view can still be denied when the environment is weak, unstable, or already stressed.

---

# 2. What Phase 5 Includes

Phase 5 includes only:

1. `RiskDecision` dataclass  
2. `position_sizer.py` helper  
3. `risk_governor.py`  
4. drawdown-aware compression hooks  
5. regime-aware compression hooks  
6. signal-strength-aware sizing  
7. replay runner integration for risk gating  

Phase 5 does **not** include:

- order execution
- stop/target simulation
- trade lifecycle management
- scorecards
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
│   ├── position_sizer.py
│   ├── regime_classifier.py
│   ├── risk_decision.py
│   ├── risk_governor.py
│   └── signal_weights.py
├── signals/
│   └── ...
└── research/
    └── replay_runner.py
```

---

# 4. Build Order

Build in this exact order:

1. `core/risk_decision.py`
2. `core/position_sizer.py`
3. `core/risk_governor.py`
4. update `research/replay_runner.py`

Do not start execution simulation before this phase passes cleanly.

---

# 5. Phase 5 Design Rules

1. Risk has veto authority over directional decisions.
2. `no_trade` remains a valid and preferred outcome when risk quality is poor.
3. Size is never derived from one factor alone.
4. Strong fusion does not automatically mean full size.
5. Unstable regimes must compress or veto risk.
6. Weak evidence must compress or veto risk.
7. Drawdown state must compress or veto risk.
8. All risk decisions must include visible reasons.

---

# 6. Size Tier Model

Phase 5 uses four tiers:

- `zero`
- `probe`
- `reduced`
- `full`

These map to notional fractions:

- `zero` → `0.00`
- `probe` → `0.10`
- `reduced` → `0.50`
- `full` → `1.00`

These are architecture defaults only.
Later phases may tune them.

---

# 7. Compression Inputs

The risk governor must evaluate:

- fused direction
- fusion score
- conflict score
- overlap penalty
- current regime
- current feature volatility
- current persistence
- replay drawdown proxy

In Phase 5, drawdown is represented as a placeholder hook so the architecture is ready for later account-state integration.

---

# 8. CAT Blocks

## 8.1 Create `renaissance_v4/core/risk_decision.py`

```bash
cat > renaissance_v4/core/risk_decision.py << 'EOF'
"""
risk_decision.py

Purpose:
Define the canonical RiskDecision object for RenaissanceV4 risk governance.

Usage:
Produced by the risk governor and consumed by replay, execution gating, and later trade logic.

Version:
v1.0

Change History:
- v1.0 Initial Phase 5 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskDecision:
    """
    Canonical output object for RenaissanceV4 risk governance.
    """
    allowed: bool
    size_tier: str
    notional_fraction: float
    compression_factor: float
    veto_reasons: list[str] = field(default_factory=list)
    debug_trace: dict[str, Any] = field(default_factory=dict)
EOF
```

---

## 8.2 Create `renaissance_v4/core/position_sizer.py`

```bash
cat > renaissance_v4/core/position_sizer.py << 'EOF'
"""
position_sizer.py

Purpose:
Provide stable size-tier to notional-fraction mapping for RenaissanceV4.

Usage:
Imported by the risk governor to convert tier decisions into normalized allocation fractions.

Version:
v1.0

Change History:
- v1.0 Initial Phase 5 implementation.
"""

from __future__ import annotations

SIZE_TIER_TO_NOTIONAL = {
    "zero": 0.00,
    "probe": 0.10,
    "reduced": 0.50,
    "full": 1.00,
}


def size_tier_to_fraction(size_tier: str) -> float:
    """
    Convert a size tier string into a notional fraction.
    Falls back to zero if an unknown tier is provided.
    """
    return SIZE_TIER_TO_NOTIONAL.get(size_tier, 0.0)
EOF
```

---

## 8.3 Create `renaissance_v4/core/risk_governor.py`

```bash
cat > renaissance_v4/core/risk_governor.py << 'EOF'
"""
risk_governor.py

Purpose:
Apply risk governance to fused directional decisions for RenaissanceV4.

Usage:
Used by the replay runner after the fusion engine has produced a directional result.

Version:
v1.0

Change History:
- v1.0 Initial Phase 5 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.feature_set import FeatureSet
from renaissance_v4.core.fusion_result import FusionResult
from renaissance_v4.core.position_sizer import size_tier_to_fraction
from renaissance_v4.core.risk_decision import RiskDecision

FULL_SIZE_FUSION_MIN = 0.90
REDUCED_SIZE_FUSION_MIN = 0.70
PROBE_SIZE_FUSION_MIN = 0.55

HIGH_VOLATILITY_VETO = 0.030
HIGH_VOLATILITY_REDUCE = 0.015

LOW_PERSISTENCE_VETO = 0.25
LOW_PERSISTENCE_REDUCE = 0.45

DRAWDOWN_PLACEHOLDER_FULL = 0.00
DRAWDOWN_PLACEHOLDER_REDUCED = 0.10
DRAWDOWN_PLACEHOLDER_ZERO = 0.20


def evaluate_risk(
    fusion_result: FusionResult,
    features: FeatureSet,
    regime: str,
    drawdown_proxy: float = 0.0,
) -> RiskDecision:
    """
    Evaluate a fused decision and return an allowed/blocked size tier with explicit reasons.
    Phase 5 uses a drawdown proxy placeholder so later phases can wire in real account state.
    """
    veto_reasons: list[str] = []
    compression_factor = 1.0
    size_tier = "zero"
    allowed = False

    if fusion_result.direction == "no_trade":
        veto_reasons.append("no_trade_from_fusion")
        return RiskDecision(
            allowed=False,
            size_tier="zero",
            notional_fraction=0.0,
            compression_factor=0.0,
            veto_reasons=veto_reasons,
            debug_trace={
                "fusion_score": fusion_result.fusion_score,
                "regime": regime,
                "drawdown_proxy": drawdown_proxy,
            },
        )

    if fusion_result.conflict_score > 0.35:
        compression_factor *= 0.50
        veto_reasons.append("conflict_score_elevated")

    if fusion_result.overlap_penalty > 0.10:
        compression_factor *= 0.75
        veto_reasons.append("overlap_penalty_elevated")

    if regime == "unstable":
        compression_factor = 0.0
        veto_reasons.append("unstable_regime")
    elif regime == "volatility_expansion":
        compression_factor *= 0.75
        veto_reasons.append("volatility_expansion_compression")

    if features.volatility_20 >= HIGH_VOLATILITY_VETO:
        compression_factor = 0.0
        veto_reasons.append("volatility_too_high")
    elif features.volatility_20 >= HIGH_VOLATILITY_REDUCE:
        compression_factor *= 0.50
        veto_reasons.append("volatility_compression_applied")

    if features.directional_persistence_10 <= LOW_PERSISTENCE_VETO:
        compression_factor = 0.0
        veto_reasons.append("persistence_too_low")
    elif features.directional_persistence_10 <= LOW_PERSISTENCE_REDUCE:
        compression_factor *= 0.60
        veto_reasons.append("persistence_compression_applied")

    if drawdown_proxy >= DRAWDOWN_PLACEHOLDER_ZERO:
        compression_factor = 0.0
        veto_reasons.append("drawdown_proxy_block")
    elif drawdown_proxy >= DRAWDOWN_PLACEHOLDER_REDUCED:
        compression_factor *= 0.50
        veto_reasons.append("drawdown_proxy_reduction")

    effective_score = fusion_result.fusion_score * compression_factor

    if compression_factor <= 0.0:
        size_tier = "zero"
    elif effective_score >= FULL_SIZE_FUSION_MIN and drawdown_proxy <= DRAWDOWN_PLACEHOLDER_FULL:
        size_tier = "full"
    elif effective_score >= REDUCED_SIZE_FUSION_MIN:
        size_tier = "reduced"
    elif effective_score >= PROBE_SIZE_FUSION_MIN:
        size_tier = "probe"
    else:
        size_tier = "zero"
        veto_reasons.append("effective_score_below_probe_floor")

    notional_fraction = size_tier_to_fraction(size_tier)
    allowed = size_tier != "zero"

    decision = RiskDecision(
        allowed=allowed,
        size_tier=size_tier,
        notional_fraction=notional_fraction,
        compression_factor=compression_factor,
        veto_reasons=[] if allowed else veto_reasons,
        debug_trace={
            "fusion_direction": fusion_result.direction,
            "fusion_score": fusion_result.fusion_score,
            "effective_score": effective_score,
            "conflict_score": fusion_result.conflict_score,
            "overlap_penalty": fusion_result.overlap_penalty,
            "volatility_20": features.volatility_20,
            "directional_persistence_10": features.directional_persistence_10,
            "regime": regime,
            "drawdown_proxy": drawdown_proxy,
            "raw_veto_reasons": veto_reasons,
        },
    )

    print(
        "[risk_governor] Risk decision "
        f"allowed={decision.allowed} size_tier={decision.size_tier} "
        f"notional_fraction={decision.notional_fraction:.2f} "
        f"compression_factor={decision.compression_factor:.4f} "
        f"reasons={veto_reasons}"
    )

    return decision
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
Run directly after Phases 1 through 5 are installed to validate market-state, feature, regime, signal, fusion, and risk logic.

Version:
v5.0

Change History:
- v1.0 Initial Phase 1 replay shell.
- v2.0 Added MarketState builder, feature engine, and regime classifier integration.
- v3.0 Added signal evaluation layer integration.
- v4.0 Added fusion engine integration and no-trade threshold logic.
- v5.0 Added risk governor integration and execution gating.
"""

from __future__ import annotations

import uuid

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.fusion_engine import fuse_signal_results
from renaissance_v4.core.market_state_builder import build_market_state
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
    Build MarketState, FeatureSet, regime, signal outputs, fused decision, and risk decision.
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

        # Placeholder drawdown proxy for architecture validation.
        # Later phases should replace this with real rolling account-state drawdown.
        drawdown_proxy = 0.0

        risk_decision = evaluate_risk(
            fusion_result=fusion_result,
            features=features,
            regime=regime,
            drawdown_proxy=drawdown_proxy,
        )

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
            risk_budget=risk_decision.notional_fraction,
            execution_allowed=risk_decision.allowed,
            reason_trace={
                "phase": "phase_5_risk_governance",
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
                f"execution_allowed={decision.execution_allowed}"
            )

    print("[replay] Phase 5 replay completed successfully")


if __name__ == "__main__":
    main()
EOF
```

---

# 9. Run Sequence

Run this after Phases 1, 2, 3, and 4 are already working:

```bash
python3 renaissance_v4/research/replay_runner.py
```

Phase 5 reuses the same Phase 1 dataset and the Phase 2–4 pipeline.

---

# 10. Expected Proof

Phase 5 is complete only when:

- replay still loads the dataset cleanly
- MarketState, FeatureSet, regime, signal, and fusion output continue to work
- every eligible replay step produces a risk decision
- strong fused setups can become `probe`, `reduced`, or `full`
- weak or unstable setups are vetoed to `zero`
- logs clearly show compression factor and veto reasons
- the run completes end-to-end without failure

---

# 11. What Comes After Phase 5

Only after this passes do we move to:

- execution manager
- stop/target policy
- same-bar ambiguity handling
- trade state lifecycle
- simulated entry and exit outcomes

That will be Phase 6.

---

# 12. Final Statement

Phase 5 is where RenaissanceV4 stops pretending every directional opinion deserves capital.

It now knows how to say:

- direction may exist
- but allocation may still be denied

That is the requirement before execution logic is allowed to enter the system.
