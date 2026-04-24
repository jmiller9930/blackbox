# GT_DIRECTIVE_023 — Learning **effectiveness** proof (read-only audit)

**Date:** 2026-04-24  
**Status:** **Accepted v1 / CLOSED** — report module + HTTP + tests + operator proof in repo. **Does not** change Student runtime, grading, L3, or learning append paths.  
**From:** Product / Architect  
**To:** Engineering  
**CC:** Product, Referee, Data  
**Scope:** `renaissance_v4/game_theory/student_proctor/learning_effectiveness_report_v1.py`, `web_app.py` routes, `docs/proof/exam_v1/GT_DIRECTIVE_023_learning_effectiveness_v1.md`, tests.

---

## Objective

Prove (or fail to prove) with **persisted artifacts only** whether the Student **improves over time**, **benefits from memory profiles vs baseline**, whether **promoted** learning rows correlate with **better next runs**, and whether **LLM profile** beats **memory stub** on the same scorecard facts.

---

## Inputs (read-only)

| Artifact | Role |
|----------|------|
| `batch_scorecard.jsonl` | Primary time series: `job_id`, `status`, timestamps, E/P (exam or proxy), `exam_pass_v1`, brain profile. |
| `student_learning_records_v1.jsonl` | Promotion counts per `run_id`, governance decision histogram. |
| `training_dataset_v1.jsonl` | Optional: **line count** cross-check only (no row join in v1 report). |

**Forbidden:** re-grade, re-run L3, mutate JSONL, infer fields not on lines.

---

## Output

- **Schema:** `learning_effectiveness_report_v1` (`contract_version` = **1**).  
- **Default file:** `<pml_runtime_root>/student_learning/learning_effectiveness_report_v1.json`.  
- **Override:** `PATTERN_GAME_LEARNING_EFFECTIVENESS_REPORT_V1`.

**Determinism:** fingerprints sorted lexicographically; runs within fingerprint sorted by `(started_at_utc|ended_at_utc, job_id)`; materialized JSON uses `sort_keys=True`. `generated_at_utc` is audit metadata (tests freeze it for byte-identical checks).

---

## HTTP API

| Method | Path | Behaviour |
|--------|------|------------|
| **GET** | `/api/training/learning-effectiveness` | Full report JSON (`ok`, report fields). |
| **GET** | `/api/training/learning-effectiveness?summary=1` | Same metrics; omits per-run `runs_ordered_v1`; adds `n_runs_in_series_v1` per fingerprint. |
| **POST** | `/api/training/learning-effectiveness/materialize` | Body `{ "confirm": "MATERIALIZE_LEARNING_EFFECTIVENESS_REPORT_V1" }` writes default path (temp + rename). |

Paths resolve like other Student training routes: **`PATTERN_GAME_STUDENT_LEARNING_STORE`**, **`PATTERN_GAME_MEMORY_ROOT`** for scorecard default.

---

## Verdict (`verdict_v1`)

Heuristic **read-only** gate: improving if any of: more fingerprints with **positive E slope** than negative; **majority** of per-fingerprint **memory vs baseline** mean-E deltas &gt; 0; or **mean** LLM-vs-memory E delta &gt; 0 across fingerprints with computable deltas. Otherwise **`not_improving_or_inconclusive`**.

Product decision: do **not** proceed to training on **`not_improving_or_inconclusive`** alone.

---

## Proof + tests

- **Tests:** `renaissance_v4/game_theory/tests/test_gt_directive_023_learning_effectiveness_v1.py`  
- **Operator proof:** `docs/proof/exam_v1/GT_DIRECTIVE_023_learning_effectiveness_v1.md`

---

## Closeout (§18.3)

Commit, **pull** `main`, **push** `main`, bump **`PATTERN_GAME_WEB_UI_VERSION`** when routes change, **`gsync`** / stack restart, HTTP verify `GET /api/training/learning-effectiveness?summary=1`.
