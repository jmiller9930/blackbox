# D13 — Student panel (curriculum: trade grain)

## Summary

**Operator vocabulary (all levels):** see **`STUDENT_PANEL_DICTIONARY_v1.md`** and in-browser **`/docs/student-panel-dictionary`** on the Pattern Machine Flask app.

The **current curriculum** treats one **slice** as one **trade opportunity** (`trade_id` / `graded_unit_id`). The Student panel L2 view is a **single panel** with:

1. **Run summary band** (one horizontal row of aggregates + Groundhog cues).
2. **Trade carousel** below it (one focused card per closed trade from `replay_outcomes_json`).

L3 is a **per-trade** deep dive using **`student_decision_record_v1`** (Student vs Referee vs baseline vs context; **`data_gap`** when a field is not exported).

## On-disk artifact

When parallel batches run with session logging enabled, each `logs/batch_<UTC>_<id>/` folder includes:

| File | Purpose |
|------|---------|
| `BATCH_README.md` | Human index |
| `<scenario>/run_record.json` | Per-scenario run memory snapshot |
| **`batch_parallel_results_v1.json`** | Full parallel worker rows, including **`replay_outcomes_json`** per scenario (required to enumerate **every trade** without inferring from scorecard-only rollups) |

Loader: `scorecard_drill.load_batch_parallel_results_v1(batch_dir)`.

## API

| Endpoint | Payload |
|----------|---------|
| `GET /api/student-panel/runs` | Run table (unchanged grain: one row per batch / job) |
| `GET /api/student-panel/l1-road` | `student_panel_l1_road_v1` — fingerprint × brain profile × `llm_model` aggregates (**GT_DIRECTIVE_016**) |
| `GET /api/student-panel/run/<job_id>/decisions` | `student_panel_d13_selected_run_v1`: `run_summary`, `slices[]` keyed by `trade_id` |
| `GET /api/student-panel/decision?job_id=&trade_id=` | `student_decision_record_v1` (alias: `decision_id=` for migration) |

Implementation: `renaissance_v4/game_theory/student_panel_d13.py`.

## Groundhog state (run summary)

Run-band **Groundhog state** follows directive rules (`COLD` / `WEAK` / `ACTIVE` / `STRONG`) using scorecard retrieval signals + harness / Student handoff behavior flags + prior-batch outcome delta where available (via `build_d11_run_rows_v1`).

## What stays scenario-scoped

`scenario_id` remains the **batch row / harness unit**. It must **not** be used as the carousel slice identity when multiple trades exist under one scenario.

## Older batches

Runs completed **before** `batch_parallel_results_v1.json` existed cannot show a truthful trade carousel; the API surfaces `data_gaps` and empty `slices` until a new batch is executed with session logging.
