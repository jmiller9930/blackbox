# Student reasoning wiring report v1

**Purpose:** Discovery snapshot before any **crypto-perps reasoning exam** layer. Describes how the **Student**, **entry reasoning (“engine”)**, **Referee replay**, **learning store**, **governance**, and **indicator/context** machinery fit together in this repo **today**.

**Scope:** Code and docs as wired in `renaissance_v4/game_theory/` (Pattern Machine learning / Student Proctor). Not an implementation plan.

---

## 1. What is the current learning engine?

In this codebase “learning” refers to **append-only persistence of Student episodes** and **governance over whether those rows participate in retrieval**, not a single neural “learning model.”

| Concept | Role | Primary code |
|--------|------|----------------|
| **Student learning store** | Append validated `student_learning_record_v1` JSONL for closed-trade episodes | `renaissance_v4/game_theory/student_proctor/student_learning_store_v1.py` (`append_student_learning_record_v1`) |
| **Reveal → row** | Build a learning row from `reveal_v1` (Student output + Referee outcome joined post-decision) | `build_student_learning_record_v1_from_reveal` in same module |
| **Lifecycle / 026C deterministic learning** | Separate track: closed lifecycle tape → deterministic learning rows (different store path) | `renaissance_v4/game_theory/student_proctor/lifecycle_deterministic_learning_026c_v1.py` |
| **Learning trace** | Append-only runtime trace (`learning_trace_events_v1.jsonl`) for proof | `renaissance_v4/game_theory/learning_trace_events_v1.py` |

There is **no** standalone service named “learning engine” that trains weights; the engine is **contract validation + JSONL append + governance filters**.

---

## 2. Where are learning records created?

- **Created** when the **Student loop seam** (`student_loop_seam_after_parallel_batch_v1` in `student_proctor_operator_runtime_v1.py`) builds `lr` via `build_student_learning_record_v1_from_reveal`, then calls `append_student_learning_record_v1(store, lr)` after governance allows storage (not rejected).

---

## 3. Where are they scored?

- **Per-trade economics / process signals** come from the **batch scorecard** and **L3 panel payload**, not from the entry reasoning pipeline assigning an “essay grade.”
- **`student_l1_process_score_v1`** (when present on the scorecard line) is used in **memory promotion** thresholds (`learning_memory_promotion_v1.promotion_process_score_min_v1`).
- **026C lifecycle** rows may carry deterministic scoring fields where implemented (`lifecycle_deterministic_learning_026c_v1`).

---

## 4. Where are they promoted or rejected?

- **`renaissance_v4/game_theory/student_proctor/learning_memory_promotion_v1.py`**
  - `classify_trade_memory_promotion_v1(l3_payload, scorecard_entry)` returns `promote` | `hold` | `reject` plus `learning_governance_v1`.
  - Reject/hold reasons include L3 **data gaps**, incomplete batch/decision records, weak expectancy, insufficient sample, low process score, warnings.
- **Retrieval eligibility:** `memory_retrieval_eligible_v1(record)` — default retrieval only includes **promote** (or legacy rows without governance).

---

## 5. Where are they retrieved later?

- **`cross_run_retrieval_v1.build_student_decision_packet_v1_with_cross_run_retrieval`** reads prior rows from the Student learning store, matches on **`context_signature_v1.signature_key`** (exact-key retrieval per Directive 06), and attaches **`retrieved_student_experience_v1`** slices to the packet.
- Default store path: `default_student_learning_store_path_v1()` under PML runtime (`student_learning/student_learning_records_v1.jsonl`).

---

## 6. What code owns learning governance?

- **`learning_memory_promotion_v1`** — builds `learning_governance_v1`, promotion context, and aggregates run-level decisions.
- **Directive:** `renaissance_v4/game_theory/directives/GT_DIRECTIVE_018_student_learning_loop_governance_v1.md`

---

## 7. RM’s role vs Student’s role vs Referee’s role

**Naming note:** “RM” is used in docs/APIs as **Reasoning Model / reasoning path**. In code it maps mainly to:

| Actor | Role today |
|-------|------------|
| **Referee (parallel replay workers)** | Runs scenarios, produces **authoritative closed-trade outcomes** (`replay_outcomes_json`). Student does not change those fills. |
| **Entry reasoning engine (`run_entry_reasoning_pipeline_v1`)** | **Deterministic** pipeline on the Student packet bars: loads bars → `indicator_context_eval_v1` → memory scoring from **retrieved** slices → prior outcomes → risk strings → **decision synthesis** (`decision_synthesis_v1.action`). Produces **`entry_reasoning_eval_v1`** used as **engine authority** when merging into Student output. |
| **Unified reasoning router** | Optional **routing / external API policy** (local vs escalation); advisory ledger — not the same as “grades learning rows.” |
| **Student (shadow / LLM)** | Produces **`student_output_v1`** (JSON). **Ollama path** uses **only the pre-reveal packet JSON** in the user prompt (plus instructions), capped (~12k chars) — see `student_ollama_student_output_v1.emit_student_output_via_ollama_v1`. After validation, **`apply_engine_authority_to_student_output_v1`** aligns direction/confidence with **`entry_reasoning_eval_v1`** and attaches it into the sealed line. |

So: **Referee = truth path for outcomes; entry reasoning = deterministic “engine” context from bars + retrieval; Student LLM = thesis JSON from packet-only prompt; merge = engine overrides stated action when rules say so.**

---

## 8. What is DATA expected to validate?

| Layer | Validates |
|-------|-----------|
| **Pre-reveal** | `validate_pre_reveal_bundle_v1` — forbidden outcome keys must not appear in packet (`contracts_v1`). |
| **Packet** | `validate_student_decision_packet_v1` — schema, causal bars, optional retrieval slices / annex. |
| **Student output** | `validate_student_output_v1`, optional directional thesis for LLM profile. |
| **Learning row** | `validate_student_learning_record_v1`. |
| **Governance** | L3 `data_gaps`, scorecard fields, decision record completeness (`classify_trade_memory_promotion_v1`). |

---

## 9. What is wired into the Student decision packet?

### 9.1 Exact fields on `student_decision_packet_v1` (as built / validated)

**Always from `build_student_decision_packet_v1`** (`student_context_builder_v1.py`):

- `schema` → `"student_decision_packet_v1"`
- `contract_version`
- `symbol`
- `table` (e.g. `market_bars_5m`)
- `candle_timeframe_minutes` (5 / 15 / 60 / 240)
- `candle_timeframe_base_source_table`
- `decision_open_time_ms`
- `graded_unit_type_hint`
- `bars_inclusive_up_to_t` (list of OHLCV dicts)
- `bar_count`
- Optional: `candle_timeframe_rollup_audit_v1` (when TF ≠ 5), `builder_notes`

**Added by cross-run retrieval** (`build_student_decision_packet_v1_with_cross_run_retrieval`):

- `retrieved_student_experience_v1` — list of `student_retrieval_slice_v1` (when matches exist)

**Optional annex (not filled by default builder):**

- `student_context_annex_v1` — validated by `validate_student_context_annex_v1`; buckets: `price_context`, `structure_context`, `indicator_context`, `time_context` (`contracts_v1` + `TRADING_CONTEXT_REFERENCE_V1.md`)

### 9.2 Indicators, market regime, fusion, risk, memory, funding, prior outcomes

| Topic | In default **packet** JSON shown to LLM? | Notes |
|-------|-------------------------------------------|--------|
| **Indicators (structured)** | **NO** | Not serialized into `student_decision_packet_v1` by `build_student_decision_packet_v1`. Indicator **labels and numbers** are computed later inside **`run_entry_reasoning_pipeline_v1`** as `indicator_context_eval_v1` from **`bars_inclusive_up_to_t`**. |
| **Market regime** | **NO** (as a dedicated packet field) | EMA trend / RSI state etc. appear in **`entry_reasoning_eval_v1`**, not in the raw packet. Optional future: `student_context_annex_v1`. |
| **Fusion** | **NO** | No engine-memory fusion bundle in the Student packet for this path (see `student_data_capability_audit_v1.md`). |
| **Risk (structured)** | **NO** in packet | **`risk_inputs_v1`** is produced inside **`entry_reasoning_eval_v1`** after the packet exists. |
| **Memory** | **PARTIAL** | Only if **`retrieved_student_experience_v1`** is non-empty after retrieval. |
| **Funding (perps)** | **NO** | Not present in inspected Student packet / ERE path for spot bars from `market_bars_5m`. |
| **Prior outcomes** | **NO** in packet | **`prior_outcome_eval_v1`** is computed inside **`entry_reasoning_eval_v1`** from retrieved context where implemented — not a column on the packet. |

---

## 10. Indicator / context dictionary

### 10.1 Policy / gate vocabulary (declarative strategies)

- **File:** `renaissance_v4/policy_spec/indicators_v1.py`
- **`INDICATOR_KIND_VOCABULARY`:** `ema`, `sma`, `rsi`, `atr`, `macd`, `bollinger_bands`, `vwap`, `supertrend`, `stochastic`, `adx`, `cci`, `williams_r`, `mfi`, `obv`, `parabolic_sar`, `ichimoku`, `donchian`, `volume_filter`, `divergence`, `body_measurement`, `fixed_threshold`, `threshold_group`
- **Student visibility:** **NO** — this is for **PolicySpec / Jupiter-style policy packs**, not injected into the Student Ollama prompt.

### 10.2 Entry reasoning engine labels (runtime)

- **File:** `renaissance_v4/game_theory/student_proctor/entry_reasoning_engine_v1.py`
- **`build_indicator_context_eval_v1`** emits **`indicator_context_eval_v1`** with fields such as `rsi_state`, `ema_trend`, `atr_volume_state`, `volume_state`, `normalized_state_v1`, `support_flags_v1`.
- **Example RSI states:** `continuation_pressure`, `exhaustion_risk`, `overbought`, `continuation_weakness`, `reversal_potential`, `oversold`, `neutral`
- **Example EMA trend:** `bullish_trend`, `bearish_trend`, `neutral_trend`
- **ATR volume state:** `high_volatility`, `low_volatility`, `normal_volatility`
- **Volume state:** `strong_participation`, `weak_participation` or absent

### 10.3 Docs / architecture references

- `renaissance_v4/game_theory/student_proctor/TRADING_CONTEXT_REFERENCE_V1.md` — target buckets vs today’s minimal packet
- `renaissance_v4/game_theory/student_proctor/ARCHITECTURE_BACKWARD_LADDER_STUDENT_TABLE.md`
- `renaissance_v4/game_theory/docs/student_data_capability_audit_v1.md`

### 10.4 Passed to the Student LLM?

- **Structured indicator_context_eval_v1 is NOT embedded in the Ollama user prompt.** The prompt is **instructions + `json.dumps(packet)`** (`student_ollama_student_output_v1`).
- The Student is expected to cite **packet-grounded** labels in **`supporting_indicators` / `conflicting_indicators`** per thesis rules; after seal, **`apply_engine_authority_to_student_output_v1`** overwrites **`supporting_indicators`** / **`conflicting_indicators`** / **`context_fit`** with engine-derived strings (see sealed output in traces).

---

## 11. What does the Student currently see? (one `student_test_mode_v1` decision)

**Artifact source (example job):** `runtime/student_test/bd3c87b0-8628-49da-a18c-b2eb82486182/` — evidence from `learning_trace_events_v1.jsonl` trade `student_test_0000_v1`.

| Artifact | What it contains (summary) |
|----------|----------------------------|
| **Packet fields** | Full `student_decision_packet_v1`: SOLUSDT, 5m, `decision_open_time_ms`, **`bars_inclusive_up_to_t`** as long OHLCV series (truncated in trace echo). |
| **Indicator context (in prompt)** | **Not included as a structured block** — only bars in packet JSON. |
| **Memory context** | **`retrieved_student_experience_v1`:** empty for this run (`student_retrieval_matches: 0`). |
| **Raw prompt** | `student_test_llm_turn_v1` → `evidence_payload.user_prompt_v1`: exam instructions + thesis protocol + **`Pre-reveal decision packet (JSON):`** with OHLCV. |
| **Raw LLM output** | `student_test_llm_turn_v1` → `raw_assistant_text_v1`: JSON with thesis + `supporting_indicators` / `conflicting_indicators` as model-authored strings. |
| **Sealed output** | `student_test_sealed_output_snapshot_v1` → full **`student_output_v1`** including merged **`entry_reasoning_eval_v1`** (with **`indicator_context_eval_v1`**, **`risk_inputs_v1`**, **`decision_synthesis_v1`**) and engine-aligned **`supporting_indicators`** like `rsi=continuation_pressure`, `ema_trend=bullish_trend`. |

### Inference vs structured context

- **Before seal / in prompt:** The model is asked to infer **meaning from OHLCV** (and optional protocol hooks); the prompt **does not** attach `indicator_context_eval_v1`.
- **After entry reasoning runs (same trade, in process):** Structured **`indicator_context_eval_v1`** exists and is merged into **`entry_reasoning_eval_v1`** on the sealed line.
- **Answer:** **Both**, but **sequentially**: raw bars → LLM thesis → deterministic engine evaluation → **merge** → sealed structured audit trail.

---

## 12. What does “RM” currently do? (entry reasoning + router, not learning governance)

| Question | Answer |
|----------|--------|
| Only validate/route? | **Partially.** Router validates policy/budget/key gates; **entry reasoning** **computes** scores and a **directional action**, not merely “validation.” |
| Grade reasoning (essay rubric)? | **NO** automated rubric on LLM prose quality. |
| Score learning records? | **NO** — governance uses **L3/scorecard/process score**, not ERE. |
| Decide promotion? | **NO** — **`learning_memory_promotion_v1`** decides promotion. |
| Maintain answer key / rubric? | **NO** — deterministic thresholds for synthesis (`long_threshold` / `short_threshold`) are **engine parameters**, not an exam rubric bank. |

---

## 13. What is already testable?

| Area | Tests / scripts |
|------|-------------------|
| **RM preflight** | `renaissance_v4/game_theory/tests/test_rm_preflight_wiring_v1.py` |
| **Student test mode** | `scripts/run_student_test_mode_v1.py` |
| **Authority / seal integrity** | `tests/test_learning_trace_terminal_integrity_v1.py`; `renaissance_v4/game_theory/tests/test_student_decision_authority_v1.py`; seam tests under `test_student_proctor_operator_runtime_v1.py` |
| **Decision fingerprint report** | `renaissance_v4/game_theory/tests/test_student_test_decision_fingerprint_report_v1.py` |
| **Learning promotion/rejection** | `renaissance_v4/game_theory/tests/test_gt_directive_018_learning_memory_promotion_v1.py`; `renaissance_v4/game_theory/tests/test_student_learning_loop_governance_v1.py` |
| **Memory retrieval** | `renaissance_v4/game_theory/tests/test_cross_run_retrieval_v1.py`; `renaissance_v4/game_theory/tests/test_directive_07_cross_run_proof_v1.py` |
| **Indicator context generation** | `renaissance_v4/game_theory/tests/test_gt_directive_026a_impl_entry_reasoning_engine_v1.py` (and related 026* tests) |
| **Runtime proof scripts (optional)** | `scripts/runtime_proof_acceptance_v1.py`, `scripts/student_rm_mandatory_runtime_proof_v1.py` |

---

## 14. Required YES / NO summary

| Question | YES / NO |
|----------|----------|
| Does the system already have an indicator context dictionary? | **YES** — at least two layers: **policy** vocabulary (`policy_spec/indicators_v1.py`) and **runtime** `indicator_context_eval_v1` labels (`entry_reasoning_engine_v1.py`). |
| Are those indicator meanings visible to the Student (LLM prompt)? | **NO** — not as structured fields; only **OHLCV JSON** is appended to the Ollama prompt (plus instructions). |
| Does the Student have enough structured context to reason about perps? | **NO** — **funding**, **perps-specific fields**, and **structured perps risk** are **not** in the default packet or prompt path documented here. |
| Is learning unified under RM today? | **NO** — learning store + **`learning_memory_promotion_v1`** are separate from “RM” / entry reasoning. |
| Is learning promotion gated by reasoning quality today? | **PARTIAL at best** — gated by **L3 gaps**, **scorecard economics**, **`student_l1_process_score_v1`** when present — **not** by a narrative reasoning rubric. |
| Is there already a rubric / answer-key mechanism? | **NO** — engine thresholds yes; **exam rubric** no. |
| Would adding a perps reasoning exam duplicate existing logic? | **Partially** — would **duplicate** if it re-implemented **ERE + packet contracts**; would **not** duplicate if it **extends** packet/annex + trace + governance **without** rebuilding entry reasoning from scratch. |

---

## 15. One-line

Before building a crypto-perps reasoning exam, extend the **real** architecture: **`student_decision_packet_v1` + `entry_reasoning_eval_v1` + Ollama prompt boundary + `learning_memory_promotion_v1`**, so perps fields and exams plug into the same contracts instead of a parallel grader.
