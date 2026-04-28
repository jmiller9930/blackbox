# RM Directive 1 — Quant / Perps Data & Math Capability Audit (v1)

**Directive:** [`GT_DIRECTIVE_029`](../renaissance_v4/game_theory/directives/GT_DIRECTIVE_029_directive_1_quant_perps_data_math_capability_audit_v1.md)  
**Date:** 2026-04-27  
**Kind:** Full system capability inventory — **audit only** (no implementation changes in producing this document).  
**Scope:** Pattern Machine / Student Proctor / `renaissance_v4/game_theory/` decision path; DATA ingress for student packets; related scorecards and governance. Cross-repo modules cited where relevant.

---

## Audit methodology

Claims below are from **repository reads** (grep + file inspection on branch containing this commit). “Path” is either a **filesystem path** relative to repo root or a **logical path** (HTTP route / DB table). Where something is **not** wired into `student_decision_packet_v1` or `run_entry_reasoning_pipeline_v1`, that is stated explicitly — **no planned features**.

---

## Section A — DATA_capability_v1

Legend: **YES** = present and accessible on a **documented code path** today; **NO** = not present as structured DATA feeding the Student packet builder.

| Field | YES/NO | Source | File | Path | Notes |
|-------|--------|--------|------|------|-------|
| OHLCV | **YES** | SQLite table `market_bars_5m` columns `open_time`, `symbol`, `open`, `high`, `low`, `close`, `volume` | `renaissance_v4/game_theory/student_proctor/student_context_builder_v1.py` | `fetch_bars_causal_up_to` SQL SELECT; `build_student_decision_packet_v1` → `bars_inclusive_up_to_t` | Only OHLCV (+ `open_time`). Rollup from 5m for TF 15/60/240 via `rollup_5m_rows_to_candle_timeframe`. |
| Funding rate | **NO** | — | — | — | Not loaded in `build_student_decision_packet_v1`; not in bar SELECT. |
| Open interest | **NO** | — | — | — | Same. |
| Liquidations | **NO** | — | — | — | Same. |
| Spread | **NO** | — | — | — | Same. |
| Order book | **NO** | — | — | — | Same. |
| Volume delta | **NO** | — | — | — | Bar row has scalar `volume` only; no delta series in packet builder. |
| Fills | **NO** (pre-decision packet) | — | — | — | Student packet builder explicitly does **not** load trades/fills (`student_context_builder_v1.py` docstring L129–130). Execution handoff is downstream (`build_student_execution_intent_from_sealed_output_v1` etc.), not causal OHLCV packet content. |
| Referee outcome paths | **YES** (post-decision / parallel replay) | Replay workers emit outcomes; seam builds learning rows | `renaissance_v4/game_theory/student_proctor/student_proctor_operator_runtime_v1.py` (`replay_outcomes_json` → `outcome_record_from_jsonable`); `student_learning_store_v1.append_student_learning_record_v1`; reveal builders in `student_learning_store_v1` / contracts | Outcomes attached **after** trade close for store/scorecard — **not** inside legal pre-reveal packet (`validate_pre_reveal_bundle_v1` forbids outcome keys on packet) | Referee truth for **grading** and **learning records**; never injected into pre-reveal OHLCV packet per builder contract. |

**Additional:** UI “funding” strings in `reasoning_model_operator_surface_v1.py` / `web_app.py` refer to **operator/API billing note**, not perp funding rates — **NO** market funding DATA.

---

## Section B — MATH_inventory_v1

**Classification:**

- **decision_time** — affects `decision_synthesis_v1.action` / `final_score` on the normal entry-reasoning path (before optional overrides below).
- **report_only** — scorecard, panels, exports; **does not** change sealed Student direction by itself.
- **governance_only** — promotion / hold / reject for learning store or eligibility; **does not** change `decision_synthesis_v1` formulas (may affect **whether** rows are stored or retrieved later).
- **dead_code** — not invoked from `run_entry_reasoning_pipeline_v1` / Student seam; other subsystems only.

| Formula / metric | File | Function (or location) | Classification |
|------------------|------|-------------------------|----------------|
| Wilder RSI(14) last | `renaissance_v4/game_theory/student_proctor/entry_reasoning_engine_v1.py` | `_wilder_rsi_last` | **decision_time** |
| RSI state labels (70/30 × trend) | same | `_rsi_state` | **decision_time** |
| EMA last (adaptive period) | same | `_ema_value` | **decision_time** |
| EMA trend (bull/bear/neutral) | same | `_ema_trend_state` | **decision_time** |
| True range | same | `_true_ranges` | **decision_time** |
| ATR14 Wilder-style | same | `_atr14_last` | **decision_time** |
| ATR volume bucket (high/low/normal vol) | same | `_atr_vol_state` | **decision_time** |
| Volume vs rolling mean “participation” | same | `_volume_state` | **decision_time** |
| `confidence_effect_v1.atr_adjustment` (−0.1 / +0.05 / 0) | same | `build_indicator_context_eval_v1` | **decision_time** |
| Support flags long/short/no_trade | same | `build_indicator_context_eval_v1` | **decision_time** |
| `indicator_score_v1` (±0.45 trend + RSI tweaks + ATR adj, clamp [−1,1]) | same | `indicator_score_v1` | **decision_time** |
| Memory record heuristic score | same | `score_memory_records_v1` | **decision_time** (when rows score non-empty; see Section D) |
| `memory_effect_to_score_v1` → mscore | same | `memory_effect_to_score_v1` | **decision_time** |
| `prior_outcome_eval_v1` win-fraction deltas | same | `prior_outcome_eval_v1` | **decision_time** (when `referee_outcome_subset.pnl` present on **input** records) |
| `final_score = ind_s + mscore + prior_s` + conflict clamps | same | `run_entry_reasoning_pipeline_v1` | **decision_time** |
| Thresholds long/short (`±0.2` defaults `_LONG_THRESHOLD` / `_SHORT_THRESHOLD`) | same | module constants + pipeline | **decision_time** |
| `confidence_01 = clamp(0.5 + fin * 0.4)` | same | `run_entry_reasoning_pipeline_v1` | **decision_time** |
| Risk text (invalidation/stop/target strings from ATR×multiples) | same | `build_risk_inputs_v1` | **decision_time** (gates entry if not `risk_defined`) |
| Unified reasoning router (optional) | same | `apply_unified_reasoning_router_v1` when `unified_agent_router` True | **decision_time** (mutates `entry_reasoning_eval_v1` after base pipeline) |
| `apply_engine_authority_to_student_output_v1` | same | `apply_engine_authority_to_student_output_v1` | **decision_time** (maps engine action → sealed `student_output_v1`; not a separate score formula) |
| `student_decision_authority_v1` / `maybe_apply_student_decision_authority_to_ere_v1` | `renaissance_v4/game_theory/student_proctor/student_decision_authority_v1.py` | `run_student_decision_authority_for_trade_v1`, thresholds `_SUPPRESS_ENTRY_MAX_SCORE_01`, `_PROMOTE_ENTRY_MIN_SCORE_01` vs 026c slices | **decision_time** when mode **active** and rules fire (patches `decision_synthesis_v1` on `ere` before merge) |
| Expectancy **batch** / scorecard `expectancy`, `max_drawdown` | `renaissance_v4/game_theory/pattern_game.py` | summary rollup fields | **report_only** |
| Expectancy formula discussion / row field | `renaissance_v4/game_theory/student_panel_d11.py` | `_expectancy_per_trade_for_row` | **report_only** |
| `expectancy_per_trade` in promotion | `renaissance_v4/game_theory/student_proctor/learning_memory_promotion_v1.py` | `classify_trade_memory_promotion_v1` | **governance_only** |
| Exam grading expectancy mode | `renaissance_v4/game_theory/exam_grading_service_v1.py` | `compute_exam_grade_v1` paths | **governance_only** (exam pass/fail; not entry engine) |
| `pattern_outcome_quality_v1` expectancy_per_trade | `renaissance_v4/game_theory/pattern_outcome_quality_v1.py` | module-level stats | **report_only** |
| Bundle optimizer expectancy floor | `renaissance_v4/game_theory/bundle_optimizer.py` | signal disable rules | **dead_code** (relative to Student decision packet path) |
| Sharpe / Sortino proxies | `modules/anna_training/quant_metrics.py` | various | **dead_code** for PML `decision_synthesis_v1` | Not imported by `entry_reasoning_engine_v1` or Student seam. |
| Policy vocab indicators | `renaissance_v4/policy_spec/indicators_v1.py` | vocabulary | **dead_code** unless explicitly bridged (not part of `indicator_score_v1`) |

---

## Section C — DECISION_path_v1

### What determines `decision_synthesis_v1`

Primary computation is in **`run_entry_reasoning_pipeline_v1`** (`entry_reasoning_engine_v1.py`):

1. Load `bars_inclusive_up_to_t` from packet; fail if missing (`missing_bars_inclusive_up_to_t`).
2. **`build_indicator_context_eval_v1`** → RSI/EMA/ATR/support flags.
3. **`score_memory_records_v1`** / **`memory_effect_to_score_v1`** from `retrieved_student_experience` list.
4. **`prior_outcome_eval_v1`** on same list.
5. **`build_risk_inputs_v1`**; `risk_defined_v1` gates actionable entries.
6. **`indicator_score_v1`**, combine **`fin = ind_s + mscore + prior_s`** with conflict rules (`run_entry_reasoning_pipeline_v1` ~627–645).
7. Map `fin` to **`decision_synthesis_v1.action`** ∈ `enter_long` | `enter_short` | `no_trade`.
8. Derive **`confidence_01`** and **`confidence_band`**.

Optional **same-function tail**:

9. If **`unified_agent_router`**: **`apply_unified_reasoning_router_v1`** may replace/mutate `entry_reasoning_eval_v1` (~762–791).
10. **026c fault-map merge** node only (`merge_026c_learning_retrieval_node_only_v1`) — fault map, not primary score.

## Runtime order — Student parallel batch seam

**File:** `renaissance_v4/game_theory/student_proctor/student_proctor_operator_runtime_v1.py`

**Order for each trade (representative path):**

1. **`build_student_decision_packet_v1_with_cross_run_retrieval`** (or plain packet build) → `pkt`.
2. **`run_entry_reasoning_pipeline_v1`** (`student_decision_packet=pkt`, `retrieved_student_experience=rxx`) → **`ere`** (`entry_reasoning_eval_v1`).
3. **Student LLM or stub** → **`so`** (`student_output_v1` proposal), ~lines 848–967 region.
4. **`run_student_decision_authority_for_trade_v1`** → may **mutate `ere`** when authority mode **active** and 026c rules + safety pass (~978–994).
5. **`apply_engine_authority_to_student_output_v1(so, ere, …)`** → **canonical direction/action** copied from **`ere.decision_synthesis_v1`** into **`so`**; attaches `entry_reasoning_eval_v1` (~1008+).

**Authority vs engine:** Engine synthesis is in **`ere`**; **`apply_engine_authority_to_student_output_v1`** overwrites **`student_action_v1` / `act` / `direction`** to match **`decision_synthesis_v1.action`** (`entry_reasoning_engine_v1.py` ~947–992). LLM cannot override action (`validate_llm_explanation_against_entry_reasoning_v1`).

**Student role:** Produces narrative/protocol JSON **before** merge; **does not** control final action after step 5.

### Override order (summary)

| Step | Component | Effect |
|------|-----------|--------|
| 1 | Entry reasoning engine | Computes **`decision_synthesis_v1`** |
| 2 | Optional unified reasoning router | May alter **`entry_reasoning_eval_v1`** |
| 3 | Optional **`student_decision_authority_v1` (active)** | May patch **`decision_synthesis_v1.action`** / confidence on **`ere`** |
| 4 | **`apply_engine_authority_to_student_output_v1`** | **Final sealed action** aligned to **`ere`** (post authority) |

### Final action code path

**Final structured action** read by seal path is **`apply_engine_authority_to_student_output_v1`** output — driven by **`entry_reasoning_eval_v1.decision_synthesis_v1`** after steps above.

---

## Section D — MEMORY_field_usability_v1

### Full learning record schema (validated)

**Validator:** `validate_student_learning_record_v1` — `renaissance_v4/game_theory/student_proctor/contracts_v1.py` (~392–445).

**Required / checked fields include:** `schema`, `contract_version`, `record_id`, `created_utc`, `run_id`, `graded_unit_id`, `context_signature_v1` (dict), `student_output`, `referee_outcome_subset` (dict), `alignment_flags_v1` (dict), optional `candle_timeframe_minutes`, optional `learning_governance_v1`, optional others per validator.

**Legal example:** `legal_example_student_learning_record_v1()` same file (~568–585).

### Usable at decision time (pre-reveal)

| Field group | Usable at decision time | Notes |
|-------------|-------------------------|-------|
| Full `student_learning_record_v1` | **NO** | Entire row is **post-reveal** artifact; not stuffed into pre-reveal packet raw. |
| **Retrieval slice** (`student_retrieval_slice_v1`) | **Partial** | **`project_student_learning_record_to_retrieval_slice_v1`** omits `referee_outcome_subset` / `alignment_flags_v1` from slice (`cross_run_retrieval_v1.py` ~49–50). Slice contains `source_record_id`, `prior_student_output`, `signature_key`, timeframe, etc. |
| **026c lifecycle** slices on packet | **YES** when present | Separate field `FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C`; used by authority rules + fault merge — not full learning row. |

### Similarity retrieval

- **Mechanism today:** **`list_student_learning_records_by_signature_key_v1`** — **exact** `context_signature_v1.signature_key` match, capped (`cross_run_retrieval_v1.py`).
- **Similarity (embedding / distance):** **NO** — not implemented.

### Does retrieval affect scoring?

**YES** — **when** `score_memory_records_v1` receives rows with **`record_id`** and optionally **`referee_outcome_subset`** / **`candle_timeframe_minutes`**, scores feed **`memory_effect_to_score_v1`** → **`mscore`** → **`final_score`** (`entry_reasoning_engine_v1.py` ~553–629).

**Critical limitation:** Projected **`retrieved_student_experience_v1`** slices use **`source_record_id`** (see `cross_run_retrieval_v1.py` ~75) while **`score_memory_records_v1`** reads **`record_id`** (`_record_id` ~249–250). **Mismatch → rows skipped → `mscore` often 0.** Slices also omit **`referee_outcome_subset`**, so **`prior_outcome_eval_v1`** often sees **no PnL** from slices.

### Memory affects decision: **YES** (code path) **with operational caveat**

- **YES:** Memory terms are part of **`final_score`** in **`run_entry_reasoning_pipeline_v1`**.
- **Caveat:** Cross-run **packet retrieval path** as wired often **does not** supply scoring-compatible rows → **effective memory influence frequently zero** until slice shape / ID alignment is fixed (future directive — **not** implemented here).

---

## Section E — GAP_inventory_v1

| Gap | Status |
|-----|--------|
| **Unified RM façade** | **MISSING** — intelligence split across `entry_reasoning_engine_v1`, `student_decision_authority_v1`, `learning_memory_promotion_v1`, optional router. |
| **State model (probabilistic regimes)** | **MISSING** — only discrete RSI/EMA/ATR labels. |
| **EV for long/short/no-trade in entry engine** | **MISSING** — expectancy exists in scorecards/promotion/exam grading, **not** as RM EV driving `decision_synthesis_v1`. |
| **Pattern similarity (non-exact)** | **MISSING** — signature-key retrieval only. |
| **Perps-specific DATA (funding, OI, liquidations, spread, OB)** | **MISSING** from Student packet / bar pipeline. |
| **Probabilistic modeling used in decisions** | **MISSING** — no HMM/posteriors in entry path. |
| **Memory as “seen this pattern before”** | **MISSING** — heuristic score + exact key; embedding similarity **MISSING**. |
| **Reasoning quality rubric inside RM** | **PARTIAL** — protocol validation + promotion gates exist; **unified RM rubric MISSING** per Directive 0 target. |
| **Slice ↔ scorer contract alignment** | **MISSING** — `source_record_id` vs `record_id`; outcome omission from pre-reveal slices breaks prior/memory scoring from retrieval. |

No soft language: gaps are **real** until addressed by future directives.

---

## Directive 1 deliverable complete. Requesting Architect acceptance.

**Git:** merged on branch containing this document; engineer shall paste **`git rev-parse HEAD`** after push in **`GT_DIRECTIVE_029`** Engineer update section.

---

## References (index)

| Topic | Primary files |
|-------|----------------|
| Packet DATA | `student_context_builder_v1.py`, `contracts_v1.py` |
| Entry scoring | `entry_reasoning_engine_v1.py` |
| Retrieval | `cross_run_retrieval_v1.py`, `student_learning_store_v1.py` |
| Authority | `student_decision_authority_v1.py`, `student_proctor_operator_runtime_v1.py` |
| Seal merge | `entry_reasoning_engine_v1.py` (`apply_engine_authority_to_student_output_v1`) |
| Promotion | `learning_memory_promotion_v1.py` |
