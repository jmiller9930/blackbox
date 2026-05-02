# FinQuant — Operator Audit Guide

**Purpose:** A human operator or trading partner can use this document to independently
verify every decision the module made, perform the underlying math themselves, and
determine whether the automated agent is reasoning correctly.

---

## 1. What the module is

FinQuant is an automated trading decision agent. It watches a flowing stream of
15-minute SOL-PERP price bars (sourced from a live Pyth oracle feed). For each bar
it decides: enter long, enter short, or stand down.

It is **not** executing trades. It is producing governed decisions with full reasoning
trails that a human operator can audit before any execution occurs.

---

## 2. What each column in the ledger means

| Column | Meaning | How to verify |
|--------|---------|---------------|
| `timestamp` | UTC time of the 15m bar | Cross-reference against Pyth/exchange data |
| `close` | Closing price of the 15m bar in USD | Match to OHLC source |
| `rsi_14` | Relative Strength Index, 14-period | Compute: RSI = 100 − 100/(1 + avg_gain/avg_loss) over 14 bars |
| `atr_14` | Average True Range, 14-period | TR = max(high−low, abs(high−prev_close), abs(low−prev_close)); ATR = 14-period EMA of TR |
| `atr_pct` | ATR as % of close price | `atr_14 / close × 100` |
| `ema_20` | Exponential Moving Average, 20-period | EMA = close × (2/21) + prev_EMA × (19/21) |
| `regime` | Market state at decision time | See §4 below |
| `action` | What the agent decided | ENTER_LONG / ENTER_SHORT / NO_TRADE / INSUFFICIENT_DATA |
| `source` | How the decision was made | rule = rules only; llm = Qwen reasoning; hybrid = memory-backed |
| `hypothesis_1` | Primary thesis the agent argued | The case FOR the action |
| `h1_confidence` | Agent's confidence in hypothesis 1 | 0.0 = no evidence, 1.0 = very strong |
| `hypothesis_2` | Counter-thesis — strongest argument against | The case AGAINST |
| `h2_confidence` | Agent's confidence in hypothesis 2 | Must be lower than h1 for action to proceed |
| `confidence_spread` | h1_confidence − h2_confidence | If < 0.20 → INSUFFICIENT_DATA must be triggered |
| `planned_r_multiple` | Target distance ÷ stop distance | R must be ≥ 1.5 for entry to be valid |
| `outcome` | What actually happened | win / loss / no_trade_correct / no_trade_missed |
| `pnl` | Profit or loss on the trade | In price units (e.g. USD per SOL) |
| `is_good_decision` | True if the decision was correct | win OR no_trade_correct = good |

---

## 3. The prime directive — rules the agent must follow

Every decision is governed by six principles. A human auditor can check each one:

**P-1 — Never lie.** If the agent outputs `INSUFFICIENT_DATA`, it correctly admitted it
did not know. If it outputs `ENTER_LONG` with `h1_confidence = 0.3`, that is a
violation — confidence is too low.

**P-2 — Reason with tools.** The agent must cite specific indicator values in its
thesis (RSI=49.5, ATR%=4.5%, etc.). If the thesis says "price looks strong" without
citing indicators, that is a violation.

**P-3 — Risk-averse default.** If in doubt, the agent should say NO_TRADE. A high
volume of entries relative to total opportunities is a red flag.

**P-4 — Pattern similarity.** If memory records were retrieved, the agent should
reference them in its thesis. If memory is available but ignored, that is a gap.

**P-5 — Context first.** The thesis should mention the regime and RSI trajectory, not
just the current bar value. "RSI rising from 44 to 49.5 in volatile regime" is correct.
"RSI is 49.5" is insufficient.

**P-6 — Long-run math.** Optimize dollars won minus dollars lost. Many small losses
are acceptable if wins carry R ≥ 1.5. Check `planned_r_multiple` on every entry.

---

## 4. How regimes are classified

| Regime | What it means | Entry bias |
|--------|--------------|-----------|
| `trending_up` | RSI rising through bullish range, price above EMA ≥ 4 of 5 bars | Long entries more valid |
| `trending_down` | RSI falling through bearish range, price below EMA | Short entries more valid; long entries should be blocked |
| `ranging` | RSI flat near 47–53, ATR contracting | Stand down preferred |
| `volatile` | ATR% ≥ 1.5% of price | Both directions possible; R must be higher |
| `unknown` | Insufficient bar history | Stand down |

---

## 5. How to perform the math yourself (manual audit)

### RSI verification

1. Take the last 15 bars of close prices
2. Compute 14 up-moves and 14 down-moves
3. Average up-move ÷ average down-move = RS
4. RSI = 100 − (100 / (1 + RS))
5. Compare to `rsi_14` in the ledger — should match within 0.1

### ATR% verification

1. For the decision bar: TR = max(high−low, |high−prev_close|, |low−prev_close|)
2. ATR14 = EMA of TR over 14 bars (14-period EMA with k=2/15)
3. ATR% = ATR14 / close × 100
4. Compare to `atr_pct` in the ledger

### R-multiple verification

Given `planned_stop` and `planned_target` from the ledger:
- Stop distance = |entry_price − planned_stop|
- Target distance = |planned_target − entry_price|
- R = target_distance / stop_distance
- Entry is only valid when R ≥ 1.5

### Breakeven win rate

At R = 1.5 (target is 1.5× the stop):
- Breakeven win rate = 1 / (1 + R) = 1 / 2.5 = **40%**

At R = 2.0:
- Breakeven win rate = 1 / 3 = **33.3%**

This means: if the agent achieves R = 2.0 consistently, it can be profitable even
with only 34% of trades winning — as long as the wins average 2× the losses.

### Expectancy per trade

Expectancy = (win_rate × avg_win) − (loss_rate × avg_loss)

Positive expectancy = profitable over time. Compute from the PnL column:
- avg_win = average of all positive PnL rows
- avg_loss = average of absolute value of all negative PnL rows
- win_rate = wins / (wins + losses)

---

## 6. Decision quality rate — the correct headline metric

**Win rate on entries alone is misleading.**

The correct metric is: good decisions ÷ all opportunities seen.

A good decision is either:
- An entry that made money (win), OR
- Standing down when the market did not offer a valid setup (no_trade_correct)

A bad decision is either:
- An entry that lost money (loss), OR
- Standing down when the market did move favorably (no_trade_missed)

The ledger column `is_good_decision` flags each row.

**Decision quality rate** = sum(is_good_decision) / total_cases

---

## 7. Worked example — how to audit a single row

Take row from the ledger:
```
Cycle: 1
Case: seed_solperp_15m_0001
Timestamp: 2026-04-04T22:15:00Z
Close: 80.4465
RSI(14): 49.2
ATR%: 2.929%
Regime: volatile
Action: ENTER_SHORT
Source: llm
Hypothesis 1: "RSI below 50 and falling, ATR high — downward momentum building" | conf=0.62
Hypothesis 2: "Price above EMA and recent bars show recovery" | conf=0.35
Confidence spread: 0.27 (> 0.20 ✓ — entry permitted)
Planned R: 1.8 (> 1.5 ✓ — valid entry)
Outcome: win | PnL: +0.1821
```

**Human audit steps:**

1. **Check P-5 (context first):** Did the thesis mention regime? Yes — "volatile". ✓
2. **Check R-002:** spread = 0.27 ≥ 0.20. Entry permitted. ✓
3. **Check R-003:** R = 1.8 ≥ 1.5. Valid entry. ✓
4. **Check P-1:** Confidence values are specific decimals, not fabricated. ✓
5. **Verify RSI:** At close 80.45, RSI 49.2 means more recent bars have been bearish.
   Cross-reference with bar history to confirm. ✓ (confirmable from raw data)
6. **Check outcome:** Price fell after entry → SHORT was correct → win. ✓
7. **Breakeven check:** At R=1.8, breakeven win rate = 1/(1+1.8) = 35.7%.
   If the agent maintains this R consistently, it needs only 36% win rate to profit.

---

## 8. Red flags — what to look for in the ledger

| Red flag | What it means |
|----------|--------------|
| Many entries with `confidence_spread < 0.20` NOT triggering INSUFFICIENT_DATA | R-002 gate failure — agent is forcing decisions |
| Entries with `planned_r_multiple < 1.5` | R-003 violation — unfavorable risk/reward |
| `source = llm` but `hypothesis_1` is blank | Hypothesis data not captured — audit gap |
| High entry rate (> 40% of opportunities) | P-3 violation — agent not being selective |
| `regime = volatile` with ENTER_LONG entries | Agent ignoring regime context (P-5) |
| `no_trade_missed` rate > 50% | Agent is being too conservative; missing real opportunities |

---

## 9. Current performance (training run `train_20260502T205737Z_223644d3`)

| Metric | Value | Target |
|--------|-------|--------|
| Total opportunities | 200 | — |
| Decision quality rate | 44% | > 55% |
| Win rate on entries | 40% | > 50% or positive expectancy |
| Total PnL | -2.84 | > 0 |
| Entries taken | 70 / 200 = 35% | 10–25% of opportunities |
| No-trade correct | 60 / 200 = 30% | Maximize |
| No-trade missed | 70 / 200 = 35% | Minimize |

**Status:** The learning loop is running and improving. This is the baseline, not the target.
Decision quality improved from 44% to 63% across two cycles in the most recent test run.
The system is not yet profitable. The goal is to reach positive expectancy through more
training cycles and better memory utilization.

---

**Document version:** 1.0  
**Data source:** Pyth SOL-PERP oracle, clawbot SQLite database  
**LLM:** Qwen 2.5 7B via Ollama at 172.20.2.230  
**Updated:** 2026-05-02
