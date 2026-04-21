# D14 — gap closure proof (living)

This file tracks **proof items** from `D14_student_panel_architecture_spec_v1.md`. Do not mark a directive closed until its proof row is complete.

## Status

| Directive | Proof IDs | Status | Code / tests / artifact |
|-----------|-------------|--------|-------------------------|
| D14-1 (`student_decision_record_v1`) | P1, P2, P3 | **Partial** | P1: `D14_student_decision_record_v1_field_sources.md`. P2: `test_student_panel_d14_contract_v1.py`. P3: operator supplies fresh batch API capture. |
| D14-2 (L1 run table) | P4, P5 | **Partial** | L1 API enriches `d14_run_row_v1` via `enrich_student_panel_run_rows_d14`; P4/P5 need scorecard fixture tests + HTTP proof. |
| D14-3 (L2 panel) | P6, P7 | **Partial** | L2 uses trade carousel keys; P6 screenshot/API proof pending. P7: `test_student_panel_d14_contract_v1.py` (trade_id key). |
| D14-4 (L3 deep dive) | P8, P9 | **Partial** | UI reads flat D14 record; P8 evidence pending. |
| D14-5 (structured reasoning) | P10, P11 | **Open** | All `structured_reasoning_v1` fields are `data_gap` until exporter exists. |
| D14-6 (history vs Groundhog) | P12, P13 | **Partial** | `DELETE /api/batch-scorecard/run/<job_id>` removes scorecard lines only; Groundhog unchanged. UI wiring for delete button pending. Combined reset already exists as separate API calls. |

## Remaining `data_gap` (declared)

Per architecture spec §7: per-trade baseline, multi-trade Groundhog attribution, rich decision-time context, structured reasoning, per-trade pattern evaluation — all explicitly surfaced as `data_gap` where exports are missing.
