# GT_DIRECTIVE_017 — Operator proof: L3 `data_gaps[]` matrix (v1)

**Purpose:** Show that every L3 response includes mandatory structured **`data_gaps[]`** (field_name, producer, reason, expected_stage, severity) with **real producer** strings, **no silent omission**, and **LLM thesis / pre-seal rejection** semantics.

## HTTP

```bash
curl -sS "http://127.0.0.1:5000/api/student-panel/run/<job_id>/l3?trade_id=<trade_id>"
```

**Expect:** **200** and JSON with `schema` = `student_panel_l3_response_v1`, top-level **`data_gaps`** as an **array** (possibly empty). Replace `<job_id>` / `<trade_id>` with a completed parallel run that has `replay_outcomes_json` rows.

## Example L3 payload (truncated)

```json
{
  "schema": "student_panel_l3_response_v1",
  "ok": true,
  "job_id": "example_job_id",
  "trade_id": "example_trade_id",
  "decision_record_v1": { "schema": "student_decision_record_v1", "data_gaps": [] },
  "replay_outcome_v1": { "trade_id": "example_trade_id", "metadata": {} },
  "scorecard_line_v1": { "schema": "scorecard_line_public_subset_v1", "job_id": "example_job_id" },
  "decision_frames_v1": null,
  "l1_linkage_v1": { "schema": "student_panel_l1_linkage_v1", "job_id": "example_job_id" },
  "data_gaps": []
}
```

## At least one example per severity

| severity | field_name | producer | reason (code) |
|----------|------------|----------|----------------|
| **critical** | `student_output_thesis_bundle` | `student_llm` | `student_directional_thesis_store_missing_for_llm_profile_v1` |
| **warning** | `student_learning_record_v1` | `student_llm` | `llm_student_output_rejected_pre_seal_v1` |
| **info** | `timeframe` | `replay_engine` | `timeframe_not_exported` |

## LLM rejection example

When the scorecard line carries **`llm_student_output_rejections_v1` > 0**, brain profile is **`memory_context_llm_student`**, and the trade has **no** persisted learning row, D14 emits **`student_store_record_missing_for_trade`**; L3 **adds** (deduped by reason):

- **producer:** `student_llm`
- **reason:** `llm_student_output_rejected_pre_seal_v1`
- **severity:** `warning` (chosen so operators distinguish **reject-before-seal** from **critical** incomplete sealed thesis rows)

## Scorecard expectation flags (fixtures / future denorm)

Optional keys on a scorecard line drive **“expected but missing”** validation rows (tests + operator fixtures under `renaissance_v4/game_theory/tests/fixtures/gt_directive_017_l3_run_*_v1.json`):

- `l3_expect_student_l1_process_score_v1` → `student_l1_process_score_v1_missing`
- `l3_expect_exam_deliberation_on_scorecard_v1` → `exam_deliberation_not_on_parallel_scorecard_v1`
- `l3_expect_downstream_frames_for_enter_v1` → `missing_downstream_frames_enter_parallel_v1` (when `student_action` = ENTER and outcome metadata lacks downstream digest markers)
- `l3_expect_exam_grading_on_scorecard_v1` → `missing_exam_grading_on_parallel_scorecard_v1`

## Implementation map

| Artifact | Role |
|----------|------|
| `student_panel_l3_datagap_matrix_v1.py` | `build_student_panel_l3_payload_v1`, legacy string → matrix, `derive_l3_validation_data_gaps_v1` |
| `web_app.py` | `GET /api/student-panel/run/<job_id>/l3` |
| `batch_scorecard.py` | Merges `llm_student_output_rejections_v1`, `student_llm_execution_v1` from seam observability |
| `student_panel_d14.py` | Removed three always-on placeholder gap strings (GT_017 happy path alignment) |
| `tests/test_gt_directive_017_l3_datagap_v1.py` | Automated coverage |

## Done checklist (operator)

- [ ] `curl` returns **200** with **`data_gaps`** array on a real job/trade pair.
- [ ] UI L3 (Pattern Machine) shows **matrix** rows when gaps exist (UI version **≥ 2.19.55**).
