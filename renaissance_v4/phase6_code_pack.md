# RenaissanceV4 — Phase 6 Code Pack
**System:** BlackBox  
**Authority:** Architect  
**Purpose:** Phase 6 implementation for execution simulation and trade lifecycle  
**Scope:** Execution manager, stop/target policy, lifecycle engine, and PnL simulation  
**Status:** Build after Phase 5 passes

---

# 1. Objective

Phase 6 is where the system becomes **economically real**.

This is the first phase where:

- trades are simulated
- positions are opened and closed
- PnL is calculated
- lifecycle behavior is enforced

This is still **paper-only simulation**, not live trading.

---

# 2. What Phase 6 Includes

- ExecutionManager
- TradeState object
- Stop/Target policy (ATR-based)
- Lifecycle engine (open → manage → close)
- Same-bar ambiguity handling (SL-first rule)
- PnL calculation (scaled by notional)

---

# 3. Design Rules

1. Trades must persist across bars
2. Stops NEVER widen (only tighten)
3. Same-bar ambiguity resolves to SL-first
4. PnL must reflect actual notional (not 1.0 fake size)
5. No hidden behavior — everything logged

---

# 4. Trade Lifecycle

```text
Signal → Fusion → Risk → ExecutionManager

IF execution_allowed:
    OPEN position
    SET stop + target

FOR each new bar:
    CHECK stop hit
    CHECK target hit
    UPDATE trailing stop
    CLOSE if conditions met
```

---

# 5. Stop/Target Policy (Phase 6)

Use ATR proxy:

- Stop Loss = 1.6 × ATR
- Take Profit = 4.0 × ATR

---

# 6. Same-Bar Rule (CRITICAL)

If BOTH SL and TP are inside candle range:

> Assume STOP LOSS hit first (pessimistic rule)

---

# 7. CAT Blocks

## 7.1 Create TradeState

```bash
cat > renaissance_v4/core/trade_state.py << 'EOF'
from dataclasses import dataclass

@dataclass
class TradeState:
    symbol: str
    entry_price: float
    direction: str
    stop_loss: float
    take_profit: float
    size: float
    open: bool = True
EOF
```

---

## 7.2 Create ExecutionManager

```bash
cat > renaissance_v4/core/execution_manager.py << 'EOF'
from renaissance_v4.core.trade_state import TradeState

class ExecutionManager:
    def __init__(self):
        self.current_trade = None

    def open_trade(self, price, direction, atr, size):
        if direction == "long":
            stop = price - (1.6 * atr)
            target = price + (4.0 * atr)
        else:
            stop = price + (1.6 * atr)
            target = price - (4.0 * atr)

        self.current_trade = TradeState(
            symbol="SOLUSDT",
            entry_price=price,
            direction=direction,
            stop_loss=stop,
            take_profit=target,
            size=size
        )

        print(f"[execution] OPEN {direction} @ {price} SL={stop} TP={target}")

    def evaluate_bar(self, high, low):
        if not self.current_trade or not self.current_trade.open:
            return None

        t = self.current_trade

        if t.direction == "long":
            if low <= t.stop_loss:
                t.open = False
                print("[execution] STOP LOSS HIT")
                return "stop"
            if high >= t.take_profit:
                t.open = False
                print("[execution] TAKE PROFIT HIT")
                return "target"

        else:
            if high >= t.stop_loss:
                t.open = False
                print("[execution] STOP LOSS HIT")
                return "stop"
            if low <= t.take_profit:
                t.open = False
                print("[execution] TAKE PROFIT HIT")
                return "target"

        return None
EOF
```

---

## 7.3 PnL Calculation

```bash
cat > renaissance_v4/core/pnl.py << 'EOF'
def compute_pnl(entry, exit, size, direction):
    if direction == "long":
        return (exit - entry) * size
    else:
        return (entry - exit) * size
EOF
```

---

# 8. Replay Integration (Concept)

Inside replay loop:

```python
if risk_decision.allowed:
    exec_manager.open_trade(...)

result = exec_manager.evaluate_bar(high, low)

if result:
    pnl = compute_pnl(...)
```

---

# 9. Expected Output

- Trades open and close deterministically
- PnL logs visible
- No crashes
- Same data → same trades every run

---

# 10. What Comes After Phase 6

Phase 7:

- performance metrics
- win rate tracking
- drawdown tracking
- learning loop

---

# 11. Final Statement

Phase 6 is where the system becomes **real**.

Before this:
- everything was opinion

After this:
- every decision has consequence
