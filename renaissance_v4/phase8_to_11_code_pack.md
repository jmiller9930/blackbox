# RenaissanceV4 — Phase 8–11 Code Pack (Advanced Governance & Expansion)

**System:** BlackBox  
**Authority:** Architect  
**Purpose:** Extend RenaissanceV4 beyond Phase 7 into governance, validation, and scaling  
**Scope:** Promotion system, walk-forward validation, portfolio control, multi-agent architecture  
**Status:** Post-Phase 7 expansion

---

# PHASE 8 — Promotion & Decay System

## Objective
Introduce adaptive weighting based on performance.

## Components
- promotion_engine.py
- decay_detector.py
- lifecycle_manager.py

## Rules
- Signals gain weight if expectancy > 0 and sufficient N
- Signals lose weight if negative expectancy
- Signals freeze if persistent drawdown

## CAT

```bash
cat > renaissance_v4/core/promotion_engine.py << 'EOF'
def adjust_weight(signal_name, expectancy, trades):
    if trades < 20:
        return 1.0
    if expectancy > 0:
        return 1.1
    return 0.7
EOF
```

---

# PHASE 9 — Walk-Forward Validation

## Objective
Eliminate overfitting.

## Model
- Train on window A
- Validate on window B

## CAT

```bash
cat > renaissance_v4/research/walk_forward.py << 'EOF'
def split_data(data, split=0.7):
    pivot = int(len(data) * split)
    return data[:pivot], data[pivot:]
EOF
```

---

# PHASE 10 — Portfolio Engine

## Objective
Control capital across trades.

## Components
- portfolio_manager.py

## CAT

```bash
cat > renaissance_v4/core/portfolio_manager.py << 'EOF'
class PortfolioManager:
    def __init__(self):
        self.max_exposure = 0.05

    def allow_trade(self, current_exposure):
        return current_exposure < self.max_exposure
EOF
```

---

# PHASE 11 — Multi-Agent System

## Objective
Separate system into independent agents.

## Agents
- Analyst (signals)
- Executor (risk + trades)
- Auditor (performance)

## CAT

```bash
cat > renaissance_v4/agents/analyst.py << 'EOF'
class Analyst:
    def generate_signals(self):
        print("Generating signals...")
EOF
```

---

# FINAL STATEMENT

Phases 8–11 transform RenaissanceV4 from:

a signal engine

into:

a governed, learning, capital allocation system capable of evolution.
