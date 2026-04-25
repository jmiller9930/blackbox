# GT_DIRECTIVE_026A — Student Entry Reasoning Protocol (**HARD CONTRACT REVISION**)

**Date:** 2026-04-25  
**Status:** **AUTHORITATIVE v1 (HARD CONTRACT)** — This document **replaces all prior versions** of 026A. Previous versions are **insufficient** and must not be cited for implementation.  
**From:** Architect (binding direction)  
**To:** Engineering  
**CC:** Product, Referee, Data, UI  
**Scope:** Student reasoning chain, validation authority, LLM role bounds, trace and L3 display contract. **Does not** subsume GT_DIRECTIVE_026TF (candle tape / timeframe); 026A is reasoning **on** the tape already defined elsewhere.

---

## Status (revision rationale)

Prior 026A drafts are superseded due to:

- ambiguous LLM role  
- non-deterministic memory influence  
- lack of bounded context enforcement  
- lack of algorithmic weighting rules  
- insufficient validator authority  

---

## Fault (why this revision exists)

The Student path must not depend on interpretive slack. Any production of `entry_reasoning_eval_v1` (and related objects) must be **reconstructible** from stored inputs, explicit transforms, and traces—without hidden state or LLM discretion over rules.

---

## Non-negotiable core rule

The Student’s reasoning must be **reproducible**, **bounded**, **auditable**, and **enforceable by code**.

No interpretation layer may exist without:

- explicit inputs  
- explicit transformation logic  
- explicit validation  
- explicit trace  

---

## Section 1 — Reasoning architecture (final)

The reasoning pipeline is **strictly ordered** and must execute as:

```text
market_data_loaded
→ indicator_states_computed
→ memory_retrieval_scored
→ prior_outcomes_evaluated
→ risk_assessed
→ decision_scored
→ decision_validated
→ output_sealed
```

- **No step may be skipped.**  
- **No step may reorder.**  
- **Each step must emit a trace event.**

---

## Section 2 — LLM role (fully constrained)

### LLM is NOT a decision-maker

The LLM:

- does **NOT** decide trades  
- does **NOT** override rules  
- does **NOT** invent inputs  
- does **NOT** introduce new variables  

### LLM is ONLY allowed to

- transform structured inputs → structured reasoning JSON  
- map evidence → explanation fields  
- suggest confidence (**subject to validation**)

### LLM input contract (strict)

LLM input must be **EXACTLY**:

- `indicator_context_eval_v1` (raw + normalized only)  
- `memory_context_eval_v1` (retrieved only)  
- `prior_outcome_eval_v1` (aggregated only)  
- `risk_inputs_v1` (ATR, stop logic inputs only)  

LLM must **NOT** receive:

- future data  
- derived conclusions  
- hidden state  
- external context  
- system score or outcome  

### LLM output contract

LLM must output **`entry_reasoning_eval_v1`** **ONLY** using:

- provided fields  
- existing record IDs  
- provided indicator values  

### Hard fail conditions (LLM)

Reject output if:

- references unknown field  
- references unknown memory ID  
- introduces new indicator  
- omits required fields  
- produces inconsistent action/direction  
- produces invalid confidence band  
- produces decision without risk definition  

---

## Section 3 — Indicator logic (deterministic)

Indicators are **not** interpreted freely. They must map to **explicit states**.

### RSI state machine

Base mapping:

- `RSI >= 70` → `overbought`  
- `RSI <= 30` → `oversold`  
- else → `neutral`  

**Context adjustment:**

- if `trend == bullish` **AND** `RSI >= 70` → `continuation_pressure`  
- if `trend == bearish` **AND** `RSI <= 30` → `continuation_weakness`  
- if `RSI >= 70` **AND** `trend != bullish` → `exhaustion_risk`  
- if `RSI <= 30` **AND** `trend != bearish` → `reversal_potential`  

### EMA state machine

EMA must **define trend**:

- `price > EMA` **AND** `EMA slope > 0` → `bullish_trend`  
- `price < EMA` **AND** `EMA slope < 0` → `bearish_trend`  
- else → `neutral_trend`  

Slope must be computed from **prior** EMA values.

### ATR state

ATR relative to recent average:

- `high_volatility`  
- `normal_volatility`  
- `low_volatility`  

ATR affects:

- stop distance expectation  
- confidence penalty or boost  

### Volume state

If present:

- `volume > rolling_avg` → `strong_participation`  
- `volume < rolling_avg` → `weak_participation`  

### Hard rule (indicators)

Indicators must produce:

- `normalized_state_v1`  
- `confidence_effect_v1`  
- `support_flags` (long / short / no_trade)  

**No free-text interpretation** allowed in logic paths.

---

## Section 4 — Memory algorithm (not descriptive)

Memory must be **scored numerically**.

### Memory relevance score

For each retrieved record:

```text
score =
    + similarity_score (0–1)
    + timeframe_match (1 or 0)
    + regime_match (1 or 0)
    - outcome_penalty (if prior loss)
```

### Memory effect rules

- if `score >= threshold_high` → `aligned`  
- if `threshold_low <= score < threshold_high` → `partial`  
- if conflicting outcome → `conflict`  
- if below threshold → `ignore`  

### Memory influence

Memory may only:

- adjust confidence  
- block trade  
- **never** override indicator context alone (per rules above)  

### Hard fail conditions (memory)

- using memory not retrieved  
- citing record not in retrieval set  
- memory used but no score present  
- memory effect not reflected in decision  

---

## Section 5 — Prior outcome logic

Derived **only** from retrieved memory.

### Required calculation

- `win_rate = wins / total`  
- `avg_profit = mean(pnl)`  

### Rules

- if `win_rate < threshold` **and** sample size sufficient → decrease confidence  
- if win rate high **and** alignment strong → increase confidence  
- if mixed → reduce confidence  

---

## Section 6 — Risk model (mandatory)

No entry allowed without:

- `invalidation_condition_v1`  
- `stop_basis_v1`  
- `target_basis_v1`  

### Hard rule

```text
if action != no_trade AND risk_defined_v1 == false:
    reject
```

---

## Section 7 — Decision engine (final authority)

**Decision is NOT LLM output.**

Decision is:

```text
final_score =
    indicator_score
    + memory_score
    + prior_outcome_score
    + risk_adjustment
```

### Action thresholds

- `score >= long_threshold` → `enter_long`  
- `score <= short_threshold` → `enter_short`  
- else → `no_trade`  

**LLM cannot override this.**

---

## Section 8 — Validation engine (strict)

**Reject** if **ANY** of:

- missing required field  
- inconsistent state  
- confidence mismatch  
- invalid memory usage  
- unsupported reasoning claim  
- missing risk definition  

---

## Section 9 — Trace requirements

Trace must allow: **“walk the Student’s brain step-by-step.”**

Each stage must include:

- inputs  
- outputs  
- decisions  
- reasoning summary  
- evidence  

---

## Section 10 — UI requirements (L3 ready)

L3 must display:

- what indicators said  
- what memory said  
- what conflicted  
- what was ignored  
- why decision was made  
- what would invalidate it  

**NO** UI logic should infer reasoning; UI renders **sealed** structures and trace only.

---

## Section 11 — Test requirements

Tests must prove:

- RSI behaves differently in trend vs exhaustion  
- EMA defines trend correctly  
- memory can increase/decrease confidence  
- conflicting memory blocks trade  
- hallucinated memory fails  
- missing indicators fail  
- risk missing fails  
- LLM output is rejected when invalid  
- deterministic and LLM paths produce valid objects  
- decision engine overrides LLM if conflict  

---

## Section 12 — Non-goals

**Do NOT:**

- implement trade lifecycle (beyond what this contract requires for *entry* reasoning)  
- implement hold/exit (out of scope here)  
- change execution engine (unless a separate directive)  
- add multi-timeframe logic (out of scope; see 026TF for tape)  
- allow free-text reasoning to drive logic  

---

## Final rule (reconstructibility)

**If** you cannot reconstruct the decision from:

- stored data  
- reasoning object  
- trace  

**then the system is invalid.**

---

## One-line summary

**026A** is a fully deterministic, validated reasoning engine: the **LLM** is constrained to **structured explanation**; every **decision** is derived from **explicit, testable algorithms** that can be **replayed and audited exactly**.

---

## Proof required (engineering)

- [ ] Schemas and validators for all named objects (`*_v1` above) with hard-fail conditions wired.  
- [ ] Unit tests for Section 3 state machines, Section 4 scoring, Section 5 aggregates, Section 6–7 gates.  
- [ ] Property/trace tests: full pipeline emits ordered trace; invalid LLM output rejected.  
- [ ] No merge without Section 11 coverage for critical fail paths.  

---

## Deficiencies log

*Architect / engineering append here as work proceeds.*

| Date | Deficiency | Owner | Resolution |
|------|------------|-------|-------------|
| | | | |

---

## Engineer update

*Engineer: append status, work performed, files changed, proof, gaps, and acceptance request.*

---

## Architect review

*Architect: append acceptance, rejection, or rework.*
