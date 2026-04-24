# GT_DIRECTIVE_020 — E/P operator surface and comparison

**Status:** proof for directive closure. **Depends on:** GT_DIRECTIVE_019 (scorecard denorm + L1 scalar alignment).

## L1 — exam list (`GET /api/student-panel/runs` + Pattern Machine UI)

- Table columns **`E (exam)`**, **`P (exam)`**, **`PASS`**, **`E src`**, **`P src`** with native `title` tooltips on headers and cells (`E`, `P`, `PASS`, `E/P` spelled out per global UI rule).
- **`E/tr`** remains the batch **expectancy_per_trade** rollup; when exam **E** exists, L1 banding still uses exam **E** (same as 019); the exam columns make that visible.
- Rows with a non–`data_gap` **Road** band get `data-l1-band` for a light inset outline (**A** / **B** / **baseline_ruler**).
- **`l1_road_v1.groups`** is included on the runs response so the UI can render the **fingerprint comparison** table (profile × **avg E**, **avg P**, **avg exam E**, **avg exam P**, **band**) using the **same** aggregates as band logic.

## L1 road JSON (`GET /api/student-panel/l1-road`)

- Each **`road_by_job_id_v1[job_id]`** entry now carries: **`exam_e_score_v1`**, **`exam_p_score_v1`**, **`exam_pass_v1`**, **`l1_e_value_source_v1`**, **`l1_p_value_source_v1`**, **`l1_e_scalar_v1`**, **`l1_p_scalar_v1`** (scalars used for bands).
- Each **group** may include **`group_avg_exam_e_score_v1`**, **`group_avg_exam_p_score_v1`**, **`group_exam_graded_run_count_v1`**, **`group_exam_pass_count_v1`** for explicit exam-only means.
- **Legend** entries document those keys for API consumers.

## L2 — run summary (`GET /api/student-panel/run/<job_id>/decisions`)

- **`run_summary`** merges **`exam_*`** and **`l1_*_value_source_v1`** from the same **D11** panel row as the L1 table (scorecard-backed).
- **Run summary band** (chips) adds **E (exam)**, **P (exam)**, **PASS**, **E src**, **P src** with tooltips.
- A one-line **E/P (run)** caption appears under the band when any exam field is present.

## L3 — trade deep dive (`GET /api/student-panel/run/<job_id>/l3`)

- When **`scorecard_line_v1`** includes exam or source fields, the UI lists **Exam E/P (scorecard)** with **E**, **P**, **PASS**, **E src**, **P src** and tooltips.

## Ask DATA dictionary

- Topic **`exam_ep_student_panel_gt020`** summarizes boundaries: single grading source, sources labels, L3 critical gap when grading is missing.

## Verification

- Automated: `tests/test_gt_directive_020_ep_operator_surface_v1.py` (L1 road aggregates + dictionary).
- Manual: open Pattern Machine → Student fold → Level 1 table, Level 2 run, Level 3 trade; hover **E**, **P**, **PASS**, **E/P**; confirm fingerprint comparison table matches **`GET /api/student-panel/l1-road`**.
