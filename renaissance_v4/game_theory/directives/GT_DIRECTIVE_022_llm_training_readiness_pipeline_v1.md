# GT_DIRECTIVE_022 — LLM **training readiness** pipeline (export only)

**Date:** 2026-04-24  
**Status:** **Accepted v1 / CLOSED** — export + API + tests + operator proof in repo. **Does not** train, fine-tune, or change runtime LLM, 018, L3 truth rules, or grading.  
**From:** Product / Architect  
**To:** Engineering  
**CC:** Product, Referee, UI  
**Scope:** `renaissance_v4/game_theory/student_proctor/training_export_v1.py`, `web_app.py` routes, `docs/proof/exam_v1/GT_DIRECTIVE_022_training_export_v1.md`, tests.

---

## Objective

Prepare for **future** LLM training by exporting a **governed, reproducible** dataset of high-quality Student decisions: validated sealed `student_output_v1`, proven scorecard outcomes, **018 promote** only.

---

## Non-goals (explicit)

- No model training or fine-tuning.  
- No change to Ollama prompts, temperatures, or Student emit paths.  
- No change to **GT_DIRECTIVE_018** classification logic (export **reads** governance decisions already on rows).  
- No change to **017** L3 producer matrix or “truth” rules beyond using the same scorecard + store facts export uses.

---

## Eligibility (all required)

Source: **`student_learning_records_v1.jsonl`** (validated lines only — same loader as store).

1. **`learning_governance_v1.decision == "promote"`** (case-insensitive match to canonical promote string).  
2. **Scorecard join:** `find_scorecard_entry_by_job_id(learning_row.run_id)` must exist and **`status`** (case-insensitive) **`== "done"`** — excludes running / partial runs without a line.  
3. **`student_output_v1`** passes **`validate_student_output_v1`**.  
4. **Thesis:** if scorecard **`student_brain_profile_v1`** is **`memory_context_llm_student`**, require empty errors from **`validate_student_output_directional_thesis_required_for_llm_profile_v1`** on embedded `student_output`.  
5. **Critical L3 gaps at evaluation time:** rows that reached **promote** already passed 018’s reject path (critical L3 gaps → reject, not appended). Export **does not recompute** live L3; **promote-only** filter is the archival guarantee aligned with 018 at append time.

**Excluded:** `hold`, `reject`, missing `learning_governance_v1`, non-done runs, LLM rows with incomplete thesis.

**Note:** `reject` rows are **not** present in the learning store JSONL today (seam skips append); export still filters promote explicitly.

---

## Export artifact

- **Schema:** `training_record_v1` (`contract_version` = **1** in export module).  
- **File:** `training_dataset_v1.jsonl` (NDJSON, UTF-8).  
- **Default path:** `<pml_runtime_root>/student_learning/training_dataset_v1.jsonl`.  
- **Override:** `PATTERN_GAME_TRAINING_DATASET_V1` — absolute or repo-relative path to a `.jsonl` file (parent dirs created on materialize).

**Determinism:** learning rows sorted by **`(run_id, graded_unit_id, record_id)`**; each line is **`json.dumps(..., sort_keys=True, separators=(",", ":"))`**; one shared **`exported_at_utc`** per materialize batch.

---

## HTTP API

| Method | Path | Behaviour |
|--------|------|------------|
| **GET** | `/api/training/export` | JSON: `eligible_count`, `preview` (size from `preview` query, default **5**, max **500**), `filter_stats_v1`, paths. |
| **GET** | `/api/training/export?download=1` | Response body = full eligible NDJSON attachment `training_dataset_v1.jsonl`. |
| **POST** | `/api/training/export/materialize` | JSON body `{ "confirm": "MATERIALIZE_TRAINING_DATASET_V1" }` writes default path (overwrite via temp + rename). |

Learning store path follows **`PATTERN_GAME_STUDENT_LEARNING_STORE`** / default (same as other Student APIs). Scorecard uses default **`batch_scorecard.jsonl`** resolution (**`PATTERN_GAME_MEMORY_ROOT`** when set).

---

## Proof + tests

- Proof: `docs/proof/exam_v1/GT_DIRECTIVE_022_training_export_v1.md`.  
- Tests: `renaissance_v4/game_theory/tests/test_gt_directive_022_training_export_v1.py`.

---

## Engineer update

**2026-04-24 — v1 shipped**

- `student_proctor/training_export_v1.py` — eligibility, `training_record_v1`, deterministic NDJSON, materialize.  
- `web_app.py` — `GET /api/training/export`, `POST /api/training/export/materialize`.  
- Tests + proof as above.

**Requesting architect acceptance** — directive CLOSED when proof + CI green + deploy per operator runbook.

---

## Architect review

**Status:** **Accepted v1 / CLOSED** — scope limited to export; training remains a future phase.
