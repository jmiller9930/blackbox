# GT_DIRECTIVE_019 — Exam E/P denormalized into scorecard and L1

**Status:** proof artifact for directive closure. **Scope:** data alignment only; grading rules unchanged.

## 1. Scorecard line (`batch_scorecard` / `pattern_game_batch_scorecard_v1`)

On completed lines with `exam_unit_id`, `batch_scorecard` calls `merge_exam_grading_into_scorecard_record_v1` then `annotate_l1_ep_value_sources_v1`. When grading inputs and `compute_exam_grade_v1` succeed, the line carries:

- `exam_e_score_v1` — economic scalar from the grade payload (`economic_result["value"]`), not recomputed from batch expectancy.
- `exam_p_score_v1` — `process_score` from the same call.
- `exam_pass_v1` — boolean `pass` from the same call.
- `l1_e_value_source_v1` / `l1_p_value_source_v1` — `exam_pack_grading_v1` vs proxy / `data_gap` (no silent mixing).

Older runs without `exam_unit_id` or without successful merge keep proxy E (`expectancy_per_trade`) and existing P behavior; sources label proxies explicitly.

## 2. L1 road (`build_l1_road_payload_v1`)

Group means and anchor comparisons use `line_e_value_for_l1_v1` / `line_p_value_for_l1_v1`: **exam fields first**, else batch proxy fields. Each group exposes `l1_e_value_sources_v1` and `l1_p_value_sources_v1` when the member lines use different sources (mixed graded + non-graded fingerprint scenario).

## 3. Student panel runs (`student_panel_run_row_v2`)

`build_d11_run_rows_v1` passes through `exam_e_score_v1`, `exam_p_score_v1`, `exam_pass_v1`, and the `l1_*_value_source_v1` fields. `outcome_improved` compares consecutive runs using the same L1 E scalar (exam when present). Inflight rows surface `null` for exam fields.

## 4. L3 data gap (`derive_l3_validation_data_gaps_v1`)

When a **done** scorecard entry has `exam_unit_id`, the in-memory exam unit is past early phases, committed timeline has at least one `decision_frame`, frame-0 deliberation exists, a pack grading config is registered, but **`exam_e_score_v1` is still missing** on the scorecard line, L3 adds:

- `producer`: `grading_service`
- `reason`: `exam_grading_missing_for_scored_run_v1`
- `severity`: `critical`

Structured matrix registry includes the same `reason` string for legacy code mapping if ever emitted via `data_gaps[]` strings.

## 5. API / L3 subset

`GET /api/student-panel/runs` inherits the new run-row keys from D11. `GET /api/student-panel/l1-road` reflects L1 aggregation above. L3 payload `scorecard_line_v1` public subset includes `exam_unit_id`, `exam_e_score_v1`, `exam_p_score_v1`, `exam_pass_v1`, and L1 source keys when present on the underlying scorecard entry.

## 6. Verification

Automated coverage: `tests/test_gt_directive_019_exam_ep_denorm_v1.py` (graded vs proxy E/P, mixed fingerprint sources, L3 gap, D11 fields).
