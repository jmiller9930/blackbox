# GT_DIRECTIVE_017 — Student L3: `data_gap` closure matrix + producer wiring

**Date:** 2026-04-24  
**From:** Architect (via operator product lock)  
**To:** Engineer  
**CC:** Operator  
**Scope:** `renaissance_v4/game_theory` — `student_panel_d14.py` (`build_student_decision_record_v1`), replay outcome exporters, `parallel_runner` / session batch artifacts, `D14_student_decision_record_v1_field_sources.md`.

## PRECONDITION — Student directional thesis (LLM profile) **CLOSED**

Engineering **shipped** the **§1.0.2 thesis enforcement** precondition (operator memo 2026-04-24; commit message `fix(student): enforce directional thesis for LLM profile (precondition for GT_DIRECTIVE_017)`):

- ``memory_context_llm_student`` → ``student_output_v1`` **must** include thesis fields or **reject** before seal (no silent stub fallback).
- Thesis fields **persist** on learning rows and are **exposed on L3** payloads (``student_panel_d14``).
- Tests + proof: ``tests/test_student_output_thesis_extension_v1.py``, ``tests/test_student_ollama_thesis_enforcement_v1.py``, ``docs/proof/exam_v1/STUDENT_DIRECTIONAL_THESIS_LLM_PRECONDITION_v1.md``.

Canonical product mapping: **`STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §1.0 / §1.0.1 / §1.0.2**. **§17.1 matrix work may proceed** after operator/architect sign-off on lab verification.

## Canonical workflow record

This file is the canonical record for this directive.

Workflow:

1. Architect issues directive here.
2. Engineer reads and performs work.
3. Engineer appends response below.
4. Operator notifies Architect to review this folder.
5. Architect appends acceptance or rework below.

## Fault

**Today:** `student_decision_record_v1` correctly uses **`data_gap`** instead of inventing values, but **many** `data_gaps[]` codes are **structural** (`structured_reasoning_export_not_wired`, `per_trade_baseline_not_exported`, etc.) or **operational** (`batch_parallel_results_v1_missing`). Operators cannot **backtrack** from a strong L1 claim to a **complete** L3 audit chain until gaps are **closed with real exports**.

## Directive

### 17.1 Gap register (documentation deliverable)

Maintain a **matrix** (in this directive file **Engineer update** section until promoted to `docs/`) listing every stable **`data_gaps[]` code** emitted by `build_student_decision_record_v1` (and L2 slice builders if applicable):

| Code | Field(s) affected | Producer owner (module / artifact) | Acceptance test |
|------|-------------------|-------------------------------------|-------------------|
| `student_directional_thesis_store_missing_for_llm_profile_v1` | L3 `student_*` thesis flat fields | `student_panel_d14` — LLM profile but no learning-store row | `test_student_output_thesis_extension_v1` + D14 regression |
| `student_directional_thesis_incomplete_for_llm_profile_v1` | Same | Stored `student_output` missing required thesis keys for LLM profile | Fixture incomplete JSON + validator tests |
| *(engineer fills — remaining L3 codes)* | | | |

**Rule:** No code removes **`data_gap`** string from the vocabulary; work **eliminates reasons** for each code on the **happy path** (session logs on, seam ran, exports present).

### 17.2 Happy-path definition

For a **completed** parallel job with `session_log_batch_dir` + `batch_parallel_results_v1.json` + Student seam enabled and at least one learning row when trades exist, **L3** for an arbitrary `trade_id` from that run **must** return:

- `data_gaps` **empty** **or** only codes explicitly **allowed** by architect (listed in matrix “defer” column with rationale).

### 17.3 Priority order (suggested)

1. **`batch_parallel_results_v1_missing`** — enforce write + pointer on scorecard.  
2. **`student_store_record_missing_for_trade`** — seam ordering / run_id consistency.  
3. **`decision_time_ohlc_not_in_outcome_metadata`** — replay exports OHLC into outcome metadata.  
4. **`timeframe_not_exported`** — run record / manifest echo.  
5. **`structured_reasoning_export_not_wired`**, **`per_trade_baseline_not_exported`**, **`pattern_eval_per_trade_not_exported`** — wire real exports or split into smaller shippable directives with proof.

### 17.4 L1 / L3 honesty coupling

Document in **GT_DIRECTIVE_016** cross-ref: **L1 `Fx` = true** (or successor) **only if** L3 can clear **mandatory** gap codes for **sample trades** in CI (architect defines the sample set).

## Proof required

1. **Matrix complete** — All codes from `build_student_decision_record_v1` triaged.  
2. **Tests** — At least one integration test per **closed** gap category.  
3. **HTTP** — L3 GET for fixture job returns expected `data_gaps`.  
4. **Doc** — `D14_student_decision_record_v1_field_sources.md` updated; **§18.4** row for **GT_DIRECTIVE_017**.  
5. **Closeout** — **§18.3 GT_DIRECTIVE_009** when L3 payload or UI changes.

## Deficiencies log update

Log **GT_DIRECTIVE_017** until **Accepted**.

---

## Engineer update

**2026-04-24 — PRECONDITION (§1.0.2 LLM directional thesis)**

- **`contracts_v1`:** `THESIS_REQUIRED_FOR_LLM_PROFILE_V1` + `validate_student_output_directional_thesis_required_for_llm_profile_v1`.
- **`student_ollama_student_output_v1`:** default `require_directional_thesis_v1=True`; prompt **REQUIRED** thesis block; reject before return when incomplete.
- **`student_proctor_operator_runtime_v1`:** LLM path **no stub fallback** on Ollama/thesis failure; audit **`llm_student_output_rejections_v1`** (also under `student_llm_execution_v1` when contract echo present).
- **`student_panel_d14`:** L3 flat **`student_*`** thesis aliases + **`data_gaps`** for incomplete LLM-profile store rows.
- **Tests / fixtures / proof:** `test_student_output_thesis_extension_v1.py`, `test_student_ollama_thesis_enforcement_v1.py`, `tests/fixtures/student_output_thesis_llm_*.json`, `docs/proof/exam_v1/STUDENT_DIRECTIONAL_THESIS_LLM_PRECONDITION_v1.md`.
- **Docs:** `STUDENT_PATH` v1.26 §1.0.2; `D14_student_decision_record_v1_field_sources.md`; dictionary v1.3.

**Status:** PRECONDITION shipped — **GT_DIRECTIVE_017** matrix work may proceed per operator/architect gate.

---

## Architect review

**Status:** pending architect review
