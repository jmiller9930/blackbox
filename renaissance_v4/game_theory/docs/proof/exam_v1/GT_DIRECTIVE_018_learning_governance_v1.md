# GT_DIRECTIVE_018 — Operator proof: learning memory promotion & retrieval governance (v1)

**Purpose:** Show that completed parallel runs are **classified** (`promote` \| `hold` \| `reject`) from **L3 truth**, **scorecard economics**, and **thesis/process** signals; that **rejected** memory is **not appended** to the Student learning store; that **hold** rows are **stored but excluded** from default cross-run retrieval; and that **promoted** (or legacy) rows **remain retrievable**.

## HTTP

```bash
curl -sS "http://127.0.0.1:8765/api/student-panel/run/<job_id>/learning"
```

**Expect:** **200** and JSON `schema` = `student_panel_run_learning_payload_v1` with:

- **`learning_governance_v1`** — aggregate run decision (`promote` \| `hold` \| `reject`), `reason_codes`, `source_job_id`, `fingerprint`, `timestamp_utc`
- **`run_was_stored`** — any `student_learning_record_v1` rows exist for this `run_id` in the default store
- **`eligible_for_retrieval`** — at least one stored row is **retrieval-eligible** (promote or no governance block)
- **`per_trade`** — per-trade `learning_governance_v1` from the same classifier used at seam append time

## One promoted run (conceptual)

| Field | Example |
|-------|---------|
| `learning_governance_v1.decision` | `promote` |
| `reason_codes` | includes `promote_clean_l3_positive_economics_v1` |
| L3 | no critical/warning gaps; positive `expectancy_per_trade` on scorecard |
| Store | row appended with `learning_governance_v1` + `memory_promotion_context_v1` |
| Retrieval | row matches signature key → appears in `retrieved_student_experience_v1` |

## One held run

| Field | Example |
|-------|---------|
| `decision` | `hold` |
| `reason_codes` | e.g. `hold_weak_expectancy_v1`, `hold_l3_warning_gap_v1`, `hold_insufficient_sample_v1` |
| Store | row **is** appended (audit trail) |
| Retrieval | **excluded** by default (`list_student_learning_records_by_signature_key(..., retrieval_eligible_only=True)`) |

## One rejected run

| Field | Example |
|-------|---------|
| `decision` | `reject` |
| `reason_codes` | e.g. `reject_l3_critical_gap_v1`, `reject_l3_llm_pre_seal_v1`, `reject_l3_llm_thesis_gap_v1` |
| Store | **no** append for that trade (seam logs `memory_promotion_reject` in errors + `memory_promotion_batch_v1.per_trade[].stored=false`) |
| Retrieval | N/A (no row) |

## Retrieval behavior summary

| Stored `learning_governance_v1.decision` | Default retrieval |
|------------------------------------------|---------------------|
| *(absent — legacy rows)* | **Eligible** |
| `promote` | **Eligible** |
| `hold` | **Not eligible** |
| `reject` | *(not stored)* |

## Implementation map

| Artifact | Role |
|----------|------|
| `student_proctor/learning_memory_promotion_v1.py` | Classifier, run payload builder, `memory_retrieval_eligible_v1` |
| `student_proctor/student_proctor_operator_runtime_v1.py` | Gate `append_student_learning_record_v1`; attach governance + context |
| `student_proctor/student_learning_store_v1.py` | `retrieval_eligible_only` filter on signature listing |
| `student_proctor/contracts_v1.py` | Optional `learning_governance_v1` validation on learning records |
| `web_app.py` | `GET /api/student-panel/run/<job_id>/learning` |
| `tests/test_gt_directive_018_learning_memory_promotion_v1.py` | Automated proof |

## Tunables (env)

| Variable | Role |
|----------|------|
| `PATTERN_GAME_STUDENT_PROMOTION_E_MIN` | Expectancy must be **>** this to avoid weak-E hold (default `0.0`) |
| `PATTERN_GAME_STUDENT_PROMOTION_P_MIN` | When `student_l1_process_score_v1` is on the scorecard, promote requires `P >=` this (default `0.5`) |
| `PATTERN_GAME_STUDENT_PROMOTION_MIN_SCENARIOS` | Hold when `total_processed` **<** this (default `1`) |

## Done checklist

- [ ] `curl` returns **200** with `learning_governance_v1` + booleans on a real `job_id`.
- [ ] Seam audit JSON includes **`memory_promotion_batch_v1`** after a batch with the Student loop enabled.
