# GT_DIRECTIVE_026A — Reasoning engine implementation proof (v1)

**Status:** **IMPLEMENTED (v1)** — code: `renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1`  
**Tests:** `renaissance_v4/game_theory/tests/test_gt_directive_026a_impl_entry_reasoning_engine_v1.py`  
**Date:** 2026-04-25

This document satisfies the directive requirement for **worked examples** and **L3-ready payload shape** (structured fields; **no** prose that UI must parse for logic).

---

## Module map

| Component | Function / type |
|----------|------------------|
| Pipeline | `run_entry_reasoning_pipeline_v1` |
| Indicators | `build_indicator_context_eval_v1` — RSI, EMA trend, ATR state, volume |
| Memory | `score_memory_records_v1` — numeric score + `aligned\|partial\|conflict\|ignore` |
| Prior outcomes | `prior_outcome_eval_v1` — `wins_total_fraction_v1`, `avg_pnl`, confidence delta |
| Risk | `build_risk_inputs_v1` — `invalidation_condition_v1`, `stop_basis_v1`, `target_basis_v1` |
| Decision | Synthesized in pipeline — `decision_synthesis_v1` (authoritative) |
| Validation | `validate_entry_reasoning_eval_v1`, `validate_llm_explanation_against_entry_reasoning_v1` |
| Digest | `entry_reasoning_eval_digest_v1` (SHA-256, canonical JSON subset) |
| LLM override guard | `apply_decision_overrides_llm_stated_action_v1` |
| Trace (runtime) | `emit_entry_reasoning_pipeline_stage_v1` in `learning_trace_instrumentation_v1` |

**Note:** The final trace stage is emitted as `entry_reasoning_sealed_v1` (distinct from the existing `student_output_sealed` from the Ollama/shadow seam) to avoid stage-name collisions in `learning_trace_events_v1.jsonl` filters.

---

## Trace stages (in order)

1. `market_data_loaded`  
2. `indicator_context_evaluated`  
3. `memory_context_evaluated`  
4. `prior_outcomes_evaluated`  
5. `risk_reward_evaluated`  
6. `decision_synthesized`  
7. `entry_reasoning_validated`  
8. `entry_reasoning_sealed_v1` (digest + seal marker)

Each in-process row includes `inputs`, `outputs`, `evidence` (see test `test_trace_stages_order`).

---

## Example: long-leaning (synthetic monotonic up series)

* **Packet:** 100 five-minute-style bars, rising closes, single symbol.  
* **Memory:** none.  
* **Expected:** `ema_trend` → `bullish_trend`, RSI state not `exhaustion_risk` in a simple uptrend, `decision_synthesis_v1.action` is `enter_long` or `no_trade` per thresholds (see engine constants).

**L3-ready fields (excerpt):**

```json
{
  "schema": "entry_reasoning_eval_v1",
  "candle_timeframe_minutes": 5,
  "indicator_context_eval_v1": { "ema_trend": "bullish_trend", "rsi_state": "…" },
  "memory_context_eval_v1": { "aggregate_memory_effect_v1": "none" },
  "prior_outcome_eval_v1": { "wins_total_fraction_v1": 0.0, "total_with_pnl": 0 },
  "risk_inputs_v1": {
    "invalidation_condition_v1": "4h close below … invalidates long",
    "stop_basis_v1": "1.2 × ATR (…) from entry",
    "target_basis_v1": "2.0 × R multiple …"
  },
  "risk_defined_v1": true,
  "decision_synthesis_v1": {
    "final_score": 0.0,
    "action": "enter_long",
    "long_threshold": 0.2
  },
  "confidence_01": 0.0,
  "entry_reasoning_eval_digest_v1": "…64 hex…"
}
```

---

## Example: short-leaning

Use `_bars_downtrend_n(100)` (see test `test_ema_trend_bull_bear`): `ema_trend` → `bearish_trend`. Action may be `enter_short` or `no_trade` subject to final score and conflict rules.

---

## Example: `no_trade`

Any run where `final_score` lies strictly between `short_threshold` and `long_threshold` (defaults −0.2 / +0.2) yields `action: no_trade`. Conflict-heavy memory or collapsed scores also map to `no_trade` in-engine.

---

## Example: memory used (aligned / partial)

* Retrieve records with **matching** `candle_timeframe_minutes` and **positive** `referee_outcome_subset.pnl` with score above thresholds — classification `aligned` or `partial` (see `score_memory_records_v1`).

---

## Example: memory rejected / conflict

* Record with **negative** `pnl` and **timeframe match** → `memory_effect_class_v1: conflict` (test `test_memory_conflict_negative_pnl`).

---

## Example: “conflicting indicators” (RSI exhaustion vs trend)

* **Exhaustion:** `_rsi_state(72, "bearish_trend")` → `exhaustion_risk` (test `test_rsi_exhaustion_differs_from_trend_bull`).  
* **Trend:** `_rsi_state(72, "bullish_trend")` → `continuation_pressure` (or `overbought` per branch).  
This proves **different** RSI semantics under trend context (deterministic, not free text).

---

## Example: validation failure

* Object with `action: enter_long` and **no** `risk_defined_v1` **true** when required → `validate_entry_reasoning_eval_v1` returns `trade_without_risk_rejected` (test `test_validation_rejects_broken_object`).

---

## Example: full reasoning trace

* In-process: third return value of `run_entry_reasoning_pipeline_v1` is `trace_stages` (list of dicts with `stage`, `inputs`, `outputs`, `evidence`).  
* With `job_id` set and `PATTERN_GAME_LEARNING_TRACE_EVENTS=1`, stages also persist via `emit_entry_reasoning_pipeline_stage_v1` (last stage uses digest prefix in evidence).

---

## LLM

* **No** model call in this module.  
* `validate_llm_explanation_against_entry_reasoning_v1` enforces: no hallucinated memory IDs, no `mystery_score`, no `stated_action` that disagrees with engine.  
* `apply_decision_overrides_llm_stated_action_v1` records `llm_rejected_v1` when a proposal disagrees (test `test_llm_cannot_override_decision`).

---

## Hard fail conditions (contract)

| Condition | Enforced by |
|----------|-------------|
| Reconstructable decision | `entry_reasoning_eval_v1` + `trace` + digest |
| No bypass of validation | `validate_entry_reasoning_eval_v1` before seal |
| LLM cannot add data | `validate_llm_explanation_against_entry_reasoning_v1` |
| Trace completeness | ordered stages; tests for stage names |
| UI does not parse prose for logic | structured fields + trace payloads |

---

## One-line

The Student entry brain is **implemented** as a **deterministic, validated** `entry_reasoning_eval_v1` builder with a **sealed digest**, **in-process trace**, optional **persistence to learning trace**, and **tests** for RSI/EMA, memory conflict, ATR, validation, and LLM guardrails.
