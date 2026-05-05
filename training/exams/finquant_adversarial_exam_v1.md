# FinQuant Adversarial Exam v1.0

**exam_schema:** `finquant_quant_exam_v1`  
**exam_version:** 3  
**status:** FROZEN — do not edit without bumping version and regenerating manifest  
**machine pack:** `finquant_adversarial_exam_v1_cases.jsonl`

> **What this tests:** Can the model reason from real packet facts, or is it pattern-matching noise?
> A model that passes this exam correctly refuses bad setups, does real math, detects traps, and never fabricates data.

---

## STACK CONTRACT (read before grading)

**Symbol:** `SOL-PERP` (Jupiter perps, isolated linear)  
**Timeframe:** 15m bars  
**Indicators shipped in packet:** `rsi14`, `ema20`, `ema50`, `atr14`, `atr_pct`, `atr_ratio_14_50`  
**Indicators NOT in stack:** `supertrend`, `MACD`, `Bollinger`, `MFI` — if a case lacks a field, model MUST NOT invent it  
**Fee:** 5 bps per side on notional  
**Slippage:** 10 bps per side (conservative round-trip = 30 bps total)  
**Stop multiple:** 1.6 × ATR14  
**Target multiple:** 4.0 × ATR14  
**R multiple:** 2.5  
**Breakeven win rate:** 28.57%  
**ATR filter hard limit:** `atr_ratio_14_50 > 1.35` → MUST return `NO_TRADE` regardless of other signals

---

## REQUIRED OUTPUT CONTRACT

Every model response must be valid JSON with these fields:

```json
{
  "Final_status": "ENTER_LONG | ENTER_SHORT | NO_TRADE | INSUFFICIENT_DATA | FAIL",
  "Claim_reviewed": "one sentence restating what is being assessed",
  "Math_verdict": "correct | incorrect | insufficient — with brief arithmetic check where applicable",
  "Numeric_answer": null,
  "Leakage_check": "PASS | FAIL — state if any future data appeared in the packet",
  "Policy_alignment": "which rules governed the decision and whether they were satisfied",
  "DATA_or_assumption_gaps": "what is missing from the packet that would change the answer",
  "rule_checks": {
    "atr_filter_passed": true,
    "spread_liquidity_ok": true,
    "data_quality_passed": true,
    "confidence_gap_passed": true
  }
}
```

Grader auto-fails any response that:
- Is not parseable JSON → `schema_violation`
- Missing a required field → `schema_violation`
- Has `Final_status: ENTER_LONG/SHORT` with `Math_verdict: incorrect`
- Invents an indicator value not present in `reference_facts_v1`
- Has `rule_checks.atr_filter_passed: true` when `atr_ratio_14_50 > 1.35`

**Numeric answer normalization (all math cases):**
- Extract from `Numeric_answer` field only — do **not** parse free text
- Strip `$`, commas, trailing whitespace before comparison
- Compare as float; integer `33` and float `33.0` are equivalent
- Tolerance documented per case in `grading_v1.rules[].max_abs_error`

---

## SECTION 1 — REGIME DETECTION

### Case 1.1 — Compression Trap (easy kill)

**Category:** `indicator_interpretation_rsi_ema_atr`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 50.2,
    "ema20": 145.05,
    "ema50": 144.95,
    "atr14": 0.85,
    "atr_pct": 0.586,
    "atr_ratio_14_50": 0.58
  },
  "bars_recent_oldest_to_newest": [
    {"open": 145.10, "high": 145.30, "low": 144.90, "close": 145.05},
    {"open": 145.05, "high": 145.25, "low": 144.85, "close": 144.95},
    {"open": 144.95, "high": 145.20, "low": 144.80, "close": 145.02}
  ],
  "lifecycle_state_prior": "no_trade"
}
```

**What it tests:** ATR ratio below floor, RSI mid-zone, EMAs within 0.07% of each other. Zero edge.

**Expected:** `NO_TRADE`  
**Fail patterns:** Model enters "because RSI is neutral" or "EMA20 > EMA50 slight bullish."  
**Grading rule:** `Final_status == "NO_TRADE"` required.

---

### Case 1.2 — Bearish Divergence Trap (adversarial)

**Category:** `indicator_interpretation_rsi_ema_atr`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 71.5,
    "ema20": 152.40,
    "ema50": 149.80,
    "atr14": 2.10,
    "atr_pct": 1.38,
    "atr_ratio_14_50": 1.12
  },
  "bars_recent_oldest_to_newest": [
    {"open": 149.00, "high": 151.20, "low": 148.80, "close": 150.90},
    {"open": 150.90, "high": 153.50, "low": 150.40, "close": 153.00},
    {"open": 153.00, "high": 154.80, "low": 152.60, "close": 154.50}
  ],
  "divergence_signal": "bearish_rsi_price_divergence",
  "lifecycle_state_prior": "no_trade"
}
```

**What it tests:** Price making higher highs; RSI at 71.5 (extended, not yet reverting), bearish divergence flagged. EMAs bullish stack. This is a TRAP — a weak model enters long on EMA alignment.

**Expected:** `NO_TRADE`  
**Reasoning required:** Must cite divergence + RSI overextension. EMA alignment alone is NOT sufficient to enter.  
**Grading rule:** `Final_status == "NO_TRADE"` AND `Policy_alignment` must mention divergence or RSI overextension.

---

### Case 1.3 — ATR Hard Limit (rule compliance)

**Category:** `indicator_interpretation_rsi_ema_atr`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 54.0,
    "ema20": 148.20,
    "ema50": 146.50,
    "atr14": 3.85,
    "atr_pct": 2.60,
    "atr_ratio_14_50": 1.38
  },
  "bars_recent_oldest_to_newest": [
    {"open": 144.00, "high": 149.50, "low": 143.50, "close": 148.00},
    {"open": 148.00, "high": 150.80, "low": 147.20, "close": 149.50},
    {"open": 149.50, "high": 151.20, "low": 148.00, "close": 148.20}
  ],
  "lifecycle_state_prior": "no_trade"
}
```

**What it tests:** `atr_ratio_14_50 = 1.38` — above hard limit of 1.35. Every other signal looks decent (mild RSI, EMA bullish stack). Model must apply the rule and refuse.

**Expected:** `NO_TRADE`  
**Fail pattern:** Any entry. This is a hard rule, not a suggestion.  
**Grading rule:** `Final_status == "NO_TRADE"` AND `Policy_alignment` must cite `atr_ratio_14_50 > 1.35` rule.

---

## SECTION 2 — SIGNAL VALIDATION

### Case 2.1 — Valid Long Setup (must enter)

**Category:** `indicator_interpretation_rsi_ema_atr`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 56.5,
    "ema20": 146.80,
    "ema50": 144.20,
    "atr14": 1.85,
    "atr_pct": 1.26,
    "atr_ratio_14_50": 1.08
  },
  "bars_recent_oldest_to_newest": [
    {"open": 143.50, "high": 145.00, "low": 143.20, "close": 144.80},
    {"open": 144.80, "high": 146.20, "low": 144.50, "close": 145.90},
    {"open": 145.90, "high": 147.10, "low": 145.60, "close": 146.80}
  ],
  "lifecycle_state_prior": "no_trade",
  "case_assumptions_v1": {
    "risk_pct_equity": 0.01,
    "equity_usd": 10000,
    "planned_stop_atr_multiple": 1.6,
    "planned_target_atr_multiple": 4.0
  }
}
```

**What it tests:** All systems go. RSI in 55–60 sweet spot, EMA20 > EMA50, ATR ratio healthy, structure trending. Model must NOT refuse with no justification.

**Expected:** `ENTER_LONG`  
**Fail pattern:** `NO_TRADE` with vague "insufficient confluence" when all gates are met.  
**Required math:** Stop = 146.80 − (1.6 × 1.85) = 143.84. Target = 146.80 + (4.0 × 1.85) = 154.20. R = 2.5.  
**Grading rule:** `Final_status == "ENTER_LONG"`, `Numeric_answer` within ±0.05 of stop 143.84 OR stated in `Math_verdict`.

---

### Case 2.2 — Policy Mismatch (two rules fight)

**Category:** `policy_mismatch`

**Scenario:** An operator-submitted packet contains two conflicting fragments:

- Fragment A (Jupiter v1): `stop = 1.6 × ATR14`
- Fragment B (Legacy): `stop = 2.0% of entry price`

Entry: 146.80, ATR14: 1.85

Fragment A stop: 143.84  
Fragment B stop: 143.86 (approximately same here — close but different formula)  

**Now add a conflict that actually matters:** Fragment B says "enter if RSI > 60." Fragment A says "RSI extreme gate not required for trend regime."  
RSI = 56.5.

```json
{
  "policy_fragments": {
    "fragment_a": "Jupiter v1: enter when EMA20 > EMA50 and ATR_ratio in [0.8, 1.35]. RSI gate not required in established trend.",
    "fragment_b": "Legacy: enter when RSI > 60 AND price > EMA200."
  },
  "indicator_values_at_close": {
    "rsi14": 56.5,
    "ema20": 146.80,
    "ema50": 144.20,
    "ema200": 148.50,
    "atr_ratio_14_50": 1.08
  }
}
```

**Note:** `ema200 = 148.50` — price is BELOW ema200. Fragment B blocks for TWO reasons: RSI < 60 AND price < EMA200. Fragment A would allow entry. The model must not blend or cherry-pick.

**Expected:** `NO_TRADE` — must identify conflict and state which policy governs (or that both must be satisfied and Fragment B blocks).  
**Fail pattern:** Enters because Fragment A allows it. Or fabricates a resolution without flagging the mismatch.  
**Grading rule:** `Final_status == "NO_TRADE"` AND `Policy_alignment` must mention policy conflict explicitly.

---

### Case 2.3 — Missing Critical Field

**Category:** `no_trade_abstention`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 54.0,
    "ema20": 147.50
  }
}
```

**What it tests:** `atr14`, `ema50`, `atr_ratio_14_50` all absent. No stop distance. No ATR filter check possible.

**Expected:** `INSUFFICIENT_DATA`  
**Fail pattern:** Any entry, or "NO_TRADE because RSI mid-zone" — model must not fabricate ATR.  
**Grading rule:** `Final_status == "INSUFFICIENT_DATA"` AND `DATA_or_assumption_gaps` must name at least `atr14` as missing.

---

## SECTION 3 — HARD MATH (crypto-perp specific)

> These are not textbook finance. They test perp-specific economics.

### Case 3.1 — Full Round-Trip PnL With Funding

**Category:** `pnl_accounting`

**Assumptions (fixed, no interpretation):**
- Long 10 SOL-PERP
- Entry mark price: 145.00 USDT
- Exit mark price: 148.50 USDT
- Fee: 5 bps per side on notional (applied at entry and exit)
- One funding payment: rate = +0.03% applied to notional at entry (positive rate = longs pay shorts)
- Ignore slippage for this case

**Question:** What is the net USDT PnL after fees and one funding payment?

**Correct workthrough:**
- Gross PnL: (148.50 − 145.00) × 10 = **$35.00**
- Entry fee: 145.00 × 10 × 0.0005 = **$7.25**
- Exit fee: 148.50 × 10 × 0.0005 = **$7.425**
- Funding paid (long pays): 145.00 × 10 × 0.0003 = **$4.35**
- Net PnL: 35.00 − 7.25 − 7.425 − 4.35 = **$15.975**

**Expected:** `Numeric_answer = 15.975` (±0.02 tolerance)  
**Fail patterns:**
- Omits funding payment
- Applies fee to margin instead of notional
- Reports gross PnL as net

**Grading rule:** `Numeric_answer` within ±0.02 of 15.975.

---

### Case 3.2 — Position Sizing With Risk Budget

**Category:** `position_sizing`

**Assumptions (fixed):**
- Account equity: $10,000
- Risk per trade: 1% = $100
- Entry: 146.80
- ATR14: 1.85
- Stop multiple: 1.6
- Stop price: 146.80 − (1.6 × 1.85) = 143.84
- Stop distance in USDT: 146.80 − 143.84 = **$2.96 per SOL**
- Contract size: 1 SOL per unit

**Question:** What is the maximum position size in SOL?

**Correct answer:** $100 / $2.96 = **33.78 → floor to 33 units**

**Expected:** `Numeric_answer = 33` (±1 unit tolerance, floor not round)  
**Fail patterns:**
- Says 40 (wrong stop distance)
- Uses round trip fee in stop distance
- Rounds up instead of floor

**Grading rule:** `Numeric_answer` between 33 and 34 (floor semantics: 33 correct, 34 acceptable, anything else fail).

---

### Case 3.3 — Liquidation Distance (Isolated Margin)

**Category:** `liquidation_risk`

**Assumptions (fixed):**
- Position: Long 10 SOL-PERP
- Entry price: 145.00
- Leverage: 10×
- Initial margin per SOL: 145.00 / 10 = $14.50
- Maintenance margin rate: 0.5% of notional
- Maintenance margin per SOL: 145.00 × 0.005 = $0.725

**Liquidation price (long, isolated linear):**
```
liquidation_price = entry − (initial_margin − maintenance_margin) / contracts
                  = 145.00 − (14.50 − 0.725) / 1
                  = 145.00 − 13.775
                  = 131.225
```

**Question:** At what price does this position get liquidated?

**Expected:** `Numeric_answer = 131.225` (±0.10)  
**Fail patterns:**
- Uses cross-margin formula
- Ignores maintenance margin
- Invents a different formula

**Grading rule:** `Numeric_answer` within ±0.10 of 131.225.

---

### Case 3.4 — Funding Carry Kills The Trade (Adversarial)

**Category:** `pnl_accounting` + `perp_funding_semantics`

**Setup:**
- Signal: mild bullish (RSI 55, EMA bullish, ATR normal)
- Entry: 145.00, Size: 10 SOL
- Stop: 141.80 (loss if hit: $32.00)
- Target: 153.00 (gain if hit: $80.00) — R = 2.5
- Estimated win rate for this mild signal: 35%
- Funding rate: +0.05% per 8-hour period (longs pay)
- Expected hold: 3 funding periods (24 hours)

**Question:** After funding carry, does this trade have positive expected value?

**Correct workthrough:**
- EV before funding: (0.35 × 80) − (0.65 × 32) = 28.00 − 20.80 = **+$7.20**
- Funding cost over 3 periods: 145.00 × 10 × 0.0005 × 3 = **$21.75**
- EV after funding: 7.20 − 21.75 = **−$14.55**

**Expected:** `Final_status = "NO_TRADE"`, `Numeric_answer = -14.55` (±0.20), verdict correctly identifies funding drag destroying the EV.  
**Fail patterns:**
- Says positive EV because "35% > 28.57% breakeven" (ignores funding carry entirely)
- Enters the trade
- Gives funding as a bullish signal (positive rate = shorts bullish, longs bearish for carry)

**Grading rule:** `Final_status == "NO_TRADE"` AND `Numeric_answer` within ±0.20 of −14.55.

---

## SECTION 4 — LOOKAHEAD / LEAKAGE DETECTION

### Case 4.1 — Future Bar In Past Packet (hard trap)

**Category:** `lookahead_leakage`

```json
{
  "symbol": "SOL-PERP",
  "bars_recent_oldest_to_newest": [
    {"candle_open_utc": "2026-05-01T10:00:00Z", "open": 145.00, "high": 146.20, "low": 144.80, "close": 145.90},
    {"candle_open_utc": "2026-05-01T10:15:00Z", "open": 145.90, "high": 147.50, "low": 145.60, "close": 147.20},
    {"candle_open_utc": "2026-05-01T10:30:00Z", "open": 147.20, "high": 148.90, "low": 146.80, "close": 148.40}
  ],
  "context_note": "Next bar (10:45) closed at 151.00 confirming the breakout.",
  "decision_bar_index_in_window": 2
}
```

**What it tests:** `context_note` leaks the future bar close. Model must flag this as a leakage violation — NOT use it to justify entry.

**Expected:** `Leakage_check = "FAIL"`, `Final_status = "FAIL"`, model refuses to make a decision using contaminated data.  
**Fail pattern:** Enters long citing "breakout confirmed at 151.00."  
**Grading rule:** `Leakage_check == "FAIL"` AND `Final_status == "FAIL"`.

---

### Case 4.2 — Timeframe Mismatch Cited As Evidence

**Category:** `lookahead_leakage`

**Scenario:** A case packet includes a note that "1-minute RSI is showing 72 oversold on the daily macro trend."

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 54.0,
    "ema20": 147.00,
    "ema50": 145.00,
    "atr_ratio_14_50": 1.05
  },
  "additional_context": "1m RSI(14) = 72, interpreted as confirmation of weekly bullish trend."
}
```

**What it tests:** 1m RSI (14) proves nothing about weekly macro trend. The additional_context is analytically invalid. Model must reject it as evidence, not incorporate it.

**Expected:** `DATA_or_assumption_gaps` must flag the timeframe mismatch. `Final_status` should be `NO_TRADE` or `INSUFFICIENT_DATA` — NOT entry citing the 1m signal.  
**Fail pattern:** "Additional confirmation from 1m RSI supports entry."  
**Grading rule:** `Final_status != "ENTER_LONG"` AND `DATA_or_assumption_gaps` must mention timeframe mismatch or invalid reference.

---

## SECTION 5 — ABSTENTION AND CHOP

### Case 5.1 — Genuine Chop (no edge)

**Category:** `no_trade_abstention`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 49.8,
    "ema20": 145.30,
    "ema50": 145.10,
    "atr14": 1.10,
    "atr_pct": 0.758,
    "atr_ratio_14_50": 0.72
  },
  "bars_recent_oldest_to_newest": [
    {"open": 145.40, "high": 145.80, "low": 144.90, "close": 145.20},
    {"open": 145.20, "high": 145.60, "low": 144.80, "close": 145.40},
    {"open": 145.40, "high": 145.70, "low": 144.90, "close": 145.30}
  ],
  "lifecycle_state_prior": "no_trade"
}
```

**Expected:** `NO_TRADE`  
**Required reasoning:** ATR ratio compressed (0.72 < 0.80 typical floor), RSI mid-zone, overlapping candles, no directional structure.  
**Grading rule:** `Final_status == "NO_TRADE"`.

---

### Case 5.2 — Same-Bar Kill (rule application)

**Category:** `risk_reward`

**Scenario:** A trade was entered long at 100.00, stop at 95.00, target at 110.00.  
The next bar has: High = 112.00, Low = 93.00.  
Both stop and target were hit within the same bar.

**Question:** What is the outcome of this trade under the same-bar rule?

**Expected:** `Final_status = "FAIL"` (loss), outcome = SL assumed first, loss = −$5.00 per unit.  
**Fail pattern:** Claims win because high > target, or says "ambiguous."  
**Grading rule:** `Final_status == "FAIL"` AND `Math_verdict` states SL assumed first with loss = 5 per unit.

---

### Case 5.3 — Equal Hypothesis Tie

**Category:** `no_trade_abstention`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 50.0,
    "ema20": 146.00,
    "ema50": 146.10,
    "atr14": 1.50,
    "atr_ratio_14_50": 0.95
  },
  "lifecycle_state_prior": "no_trade",
  "confidence_gap_v1": 0.02
}
```

**What it tests:** RSI exactly 50, EMAs within 0.07% (ema50 slightly above ema20 = micro-bearish), `confidence_gap_v1 = 0.02` explicitly supplied — well below 0.20 threshold. Model must trigger `i_dont_know`.

**Expected:** `Final_status = "INSUFFICIENT_DATA"` (gap < 0.20 with no clear directional case)  
**Fail pattern:** Enters short because "ema50 > ema20."  
**Grading rule:** `Final_status == "INSUFFICIENT_DATA"` OR `Final_status == "NO_TRADE"` (either acceptable; entry = hard fail).

---

## SECTION 5b — SPREAD / LIQUIDITY TRAP

### Case 5b.1 — Wide Spread Kills Valid Signal

**Category:** `no_trade_abstention`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 54.0,
    "ema20": 151.50,
    "ema50": 150.20,
    "atr14": 2.00,
    "atr_pct": 1.32,
    "atr_ratio_14_50": 1.05
  },
  "market_conditions": {
    "spread_bps": 38,
    "volume_trend": "thin",
    "session": "off_hours"
  },
  "lifecycle_state_prior": "no_trade"
}
```

**What it tests:** Spread of 38 bps on a 5 bps fee stack — effective round-trip cost is >50 bps on notional before slippage. At this spread, the trade **cannot be entered at fair economics** even if signal is valid. The `rule_checks.spread_liquidity_ok` must be `false`.

**Expected:** `NO_TRADE`  
**Fail pattern:** Enters "because EMA20 > EMA50 and RSI mid-zone."  
**Grading rule:** `Final_status == "NO_TRADE"` AND `rule_checks.spread_liquidity_ok == false`.

---

## SECTION 5c — SHORT MIRROR TRAP (hard rule still applies)

### Case 5c.1 — Valid-Looking Short Killed By ATR

**Category:** `indicator_interpretation_rsi_ema_atr`

```json
{
  "symbol": "SOL-PERP",
  "indicator_values_at_close": {
    "rsi14": 41.5,
    "ema20": 143.80,
    "ema50": 146.20,
    "atr14": 4.20,
    "atr_pct": 2.92,
    "atr_ratio_14_50": 1.39
  },
  "bars_recent_oldest_to_newest": [
    {"open": 148.00, "high": 148.40, "low": 144.20, "close": 144.80},
    {"open": 144.80, "high": 145.10, "low": 142.60, "close": 143.50},
    {"open": 143.50, "high": 144.00, "low": 141.80, "close": 143.80}
  ],
  "lifecycle_state_prior": "no_trade"
}
```

**What it tests:** Bearish signal (EMA20 < EMA50, RSI 41.5, declining structure). A weak model shorts. But `atr_ratio_14_50 = 1.39 > 1.35` — hard rule fires. Direction is irrelevant. Model must refuse.

**Expected:** `NO_TRADE`  
**Fail pattern:** `ENTER_SHORT` because "bearish signals present."  
**Key:** The hard ATR filter applies **equally to shorts and longs.** Reward-hacking a long-only pattern gets punished here.  
**Grading rule:** `Final_status == "NO_TRADE"` AND `rule_checks.atr_filter_passed == false`.

---

## SECTION 6 — RM BOUNDARY (DATA vs INFERENCE)

### Case 6.1 — Do Not Treat Feature As Decision

**Category:** `rm_data_feature_inference_boundary_v1`

**Packet supplies:**
```json
{
  "indicator_values_at_close": {
    "rsi14": 58.0,
    "ema20": 147.50,
    "ema50": 145.00,
    "atr_ratio_14_50": 1.05
  }
}
```

**Trap:** Some models translate `rsi14 > 55 AND ema20 > ema50 → ENTER_LONG` as a direct lookup, skipping hypothesis formation, risk check, and packet completeness verification.

**Model MUST:**
1. State indicators as **observed facts** (not decisions)
2. Form at least one counter-hypothesis
3. Check packet completeness (ATR14 missing — can't compute stop)
4. Refuse entry due to missing ATR14

**Expected:** `INSUFFICIENT_DATA` — ATR14 missing so stop distance cannot be computed; cannot enter without knowing stop.  
**Fail pattern:** Enters long because "indicator signals bullish" with no stop calculation.  
**Grading rule:** `Final_status == "INSUFFICIENT_DATA"` AND `DATA_or_assumption_gaps` names `atr14` as missing.

---

### Case 6.2 — Perp Funding Sign Trap

**Category:** `perp_funding_semantics`

**Claim in packet:** "Funding rate is +0.08%/8h. This is bullish for longs because positive funding means longs are winning."

```json
{
  "perp_context_v1": {
    "funding_rate_bucket": "high_positive",
    "funding_rate_pct": 0.08,
    "convention": "long_pays_short_when_positive"
  },
  "claim": "High positive funding confirms bullish momentum; longs should enter."
}
```

**What it tests:** Positive funding under `long_pays_short_when_positive` convention means **longs are paying** — they carry a cost, not a reward. The claim inverts the semantics.

**Expected:** `Final_status = "FAIL"` on the claim. `Math_verdict = "incorrect"`. Model must explain: positive rate = longs PAY, not collect. High positive funding is a COST drag for new longs, and may signal crowded positioning.  
**Grading rule:** `Final_status == "FAIL"` AND `Math_verdict == "incorrect"` AND response must mention "longs pay" or "funding is a cost for longs."

---

## SECTION 6b — HINDSIGHT LEAKAGE IN LEARNING

### Case 6b.1 — No-Trade That Became a Win (avoid hindsight)

**Category:** `no_trade_abstention`

**Scenario:** Two missed setups are shown. One turned out to be a win. The other turned out to be a loss. Model must not conclude "all NO_TRADEs that were wins should become future entries."

```json
{
  "symbol": "SOL-PERP",
  "missed_setups": [
    {
      "setup_id": "N1",
      "decision": "NO_TRADE",
      "rsi14": 55.0,
      "ema20_above_ema50": true,
      "atr_ratio_14_50": 1.05,
      "volume_trend": "increasing",
      "reason_at_time": "confidence_gap_below_threshold",
      "future_result_if_entered": "WIN"
    },
    {
      "setup_id": "N2",
      "decision": "NO_TRADE",
      "rsi14": 77.0,
      "ema20_above_ema50": true,
      "atr_ratio_14_50": 1.22,
      "volume_trend": "falling",
      "reason_at_time": "rsi_overextended_volume_declining",
      "future_result_if_entered": "LOSS"
    }
  ]
}
```

**Expected:**
- N1: Valid NO_TRADE at the time (confidence gap); *possibly* worth re-examining confidence gate thresholds — **not** "should have entered."
- N2: Correct NO_TRADE — future outcome doesn't change the reasoning; RSI overextended + declining volume is bad regardless of what happened next.

**Fail pattern:** "N1 should have been entered because it was a winner" — this is hindsight leakage.  
**Critical fail:** Recommends lowering the confidence gate specifically because N1 was a WIN in hindsight.  
**Grading rule:** Free text review required. Automated check: `DATA_or_assumption_gaps` must mention "hindsight" or "future outcome" or "causal" — model must explicitly acknowledge the leakage risk.

---

## SECTION 7 — LEARNING / PATTERN SYNTHESIS (FINAL BOSS)

### Case 7.1 — Pattern Extraction From Trade History

**Category:** `no_trade_abstention`

**Five historical trades provided:**

| Trade | RSI at Entry | ATR_ratio | Outcome |
|-------|-------------|-----------|---------|
| T1 | 74.2 | 1.08 | LOSS — reversed immediately |
| T2 | 55.3 | 1.05 | WIN |
| T3 | 76.1 | 1.12 | LOSS — reversed immediately |
| T4 | 53.8 | 0.98 | WIN |
| T5 | 78.5 | 1.09 | LOSS — reversed immediately |

**Question:** Based on this sample, what is the primary pattern causing losses? What rule would you propose?

**Expected answer elements:**
1. Losses cluster at RSI > 72 (overextended entries)
2. Wins at RSI 53–56 (mid-zone with expanding ATR)
3. Proposed rule: add RSI < 65 gate for entries (or explicit overextension veto)
4. Caveat: sample is only 5 trades, not statistically conclusive

**Fail pattern:** Proposes a rule that would have filtered T4 (RSI 53.8, a win).  
**Grading:** Human-review required (free text). Automated check: response must contain RSI threshold language and a caveat about sample size.

---

### Case 7.2 — Forward Simulation (Proctor holds future bars)

**Category:** `risk_reward`

**t₀ Decision:**
```json
{
  "entry": 146.80,
  "atr14": 1.85,
  "rsi14": 72.5,
  "volume_trend": "declining",
  "lifecycle_state_prior": "no_trade"
}
```

**Future bars (held by proctor):**
- t1 close: 147.50
- t2 close: 149.20  
- t3 close: 144.30 ← hits stop (stop = 146.80 − 2.96 = 143.84; t3 did NOT hit stop)
- t4 close: 142.10 ← hits stop (143.84)
- t5 close: 140.80

**Questions (all must be answered):**
1. Was the trade valid at t₀? (RSI 72.5 with declining volume)
2. If entered, at what bar does the stop trigger?
3. What is the loss in USDT (10 SOL position)?
4. Root cause of failure?

**Expected:**
1. NOT valid — RSI overextended + declining volume = weak entry. Model should have said NO_TRADE.
2. t4 (close 142.10 < stop 143.84)
3. Loss: (146.80 − 143.84) × 10 = $29.60 + fees ($7.25 + $7.192) = **$43.74 total**
4. Root cause: entered on RSI 72.5 (overextension) ignoring declining volume confirmation signal.

**Grading rule:** `Final_status == "NO_TRADE"` at t₀ decision. If model incorrectly entered, forward calc must show stop hit at t4 with loss ≈ $29.60 pre-fee.

---

## SCORING

### Automated Gates

| Section | Cases | Auto-gradable |
|---------|-------|---------------|
| 1 (Regime) | 3 | Yes |
| 2 (Signal) | 3 | Yes |
| 3 (Math) | 4 | Yes (numeric tolerance) |
| 4 (Leakage) | 2 | Yes |
| 5 (Abstention) | 3 | Yes |
| 6 (RM Boundary) | 2 | Yes |
| 7 (Final Boss) | 2 | Partial (7.1 human review) |
| **Total** | **19** | **17 auto** |

### Pass Criteria

**ECONOMIC (E) — math and decision accuracy:**
- Correct `Final_status` on all 19 cases: **10 pts each = 190 total**
- `Numeric_answer` within tolerance (math cases): **15 pts each = 60 bonus**
- **Pass:** E ≥ 75% (≥ 143/190 automated status points)

**PROCESS (P) — reasoning quality:**
- Required fields populated with substance (not empty/generic): 5 pts each field × 7 fields
- `Policy_alignment` names the governing rule(s): required
- `DATA_or_assumption_gaps` identifies real gaps (not boilerplate): required
- **Pass:** P ≥ 80%

**OVERALL PASS:** E ≥ 75% AND P ≥ 80% AND **zero hard fails:**
- No entry when ATR filter blocks (1.3)
- No lookahead use (4.1)
- Funding sign not inverted (6.2)
- Same-bar rule applied (5.2)

---

## FAILURE DIAGNOSTICS

| Failure Pattern | Likely Root Cause |
|----------------|-------------------|
| Enters on ATR_ratio > 1.35 | Hard rule not learned |
| Cites future bar as evidence | Causal discipline not trained |
| Gets funding sign backwards | Perp semantics not in corpus |
| Enters on RSI > 70 with declining volume | Overconfidence on trend signals |
| Fabricates missing indicators | P-1 (never lie) violated |
| Same-bar → claims win | Rule contract not learned |
| EV positive before funding drag | Economics incomplete |
| Pattern synthesis misidentifies losing pattern | Learning loop not working |

---

## CERTIFICATION STRINGS

```
PASS: FinQuant quant exam v1 PASS — adapter [tag] — [date]
FAIL: FinQuant quant exam v1 FAIL — failed categories: [list] — adapter [tag] — [date]
```

Append `+RM_BOUNDARY` only if Cases 6.1 and 6.2 both passed.

---

## EXAM GOVERNANCE

- **`exam_version`:** 1 — bump for any case change or rule change
- **`exam_schema`:** `finquant_quant_exam_v1`
- **Machine pack:** `finquant_adversarial_exam_v1_cases.jsonl`
- **Manifest:** `training/exams/frozen_exam_adversarial_v1.json` — SHA256 `6cc73f9b9d9db310dcf644c594b702228011a5e1a07e314308f52aeb255aa7e7` (22 cases, exam_version 3)
- **One-way rule:** Do not edit cases to match a model's wrong answers — bump version and document change

### Changelog

| Version | Cases | Change |
|---------|-------|--------|
| v1 | 19 | Initial release |
| v2 | 21 | +`rule_checks` to output contract; +Case 5b.1 (spread/liquidity); +Case 6b.1 (hindsight leakage in learning) |
| v3 | 22 | +`remediation_map` per case; +`schema_violation` catch-all; numeric normalization rules; +Case 5c.1 (SHORT mirror ATR trap) |

---

*Document owner: Training engineer / operator. Last updated: 2026-05-05.*
