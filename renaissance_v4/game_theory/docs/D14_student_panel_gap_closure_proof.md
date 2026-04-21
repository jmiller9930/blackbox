# D14 — Student panel gap closure proof (D14.GC.1–GC.7 + §F)

This document is **artifact-backed**. Paths are repo-relative from `blackbox/` unless stated otherwise.

## GC.1 — Operator Student panel: three-level architecture only

### Implemented

- **Level 1–3 shell** lives only inside `#pgStudentPanelD11` under `#studentTriangleBody`. The operator blurb states D14 levels explicitly (`web_app.py`, Student fold).
- **D11-era seam / handoff / plumbing** is **not** in the operator body: `#pgDevStudentSeamInner`, `#pgLearningEventsStrip`, and first-trade shadow debug live under **`<details id="pgDevStudentBatchPlumbing">`**, collapsed by default (Developer — batch seam & plumbing).
- `#pgStudentHandoffStrip` removed; `studentPanelD11HandoffEl()` returns `null`; `studentPanelD11SetHandoffVisible` is a no-op for operator chrome.

### Proof artifacts

| Claim | Evidence |
|--------|-----------|
| L1 run table only (no seam DOM in operator subtree) | `renaissance_v4/game_theory/tests/test_d14_gap_closure_regression_v1.py` — `test_operator_student_triangle_body_has_only_l1_l2_l3_shell`, `test_level1_render_fn_contains_run_table_only_no_handoff_dom` |
| Level-1 JS does not inject seam/D09 HTML | Same tests inspect `web_app.py` source |

### Screenshots (operator)

Screenshots of L1/L2/L3 are **environment-specific** (browser). Capture:

1. **L1:** Student fold expanded → run table with columns including **×** delete control; no seam block above/below the table inside the panel.
2. **L2:** Click a run → run summary band + carousel only.
3. **L3:** Click a slice → one trade deep dive only.

Save under `renaissance_v4/game_theory/docs/proof/d14_gc/screenshots/` if the team tracks images in-repo (optional — not committed here).

### Open gap

None for GC.1 architecture target; developer fold remains intentionally separate.

---

## GC.2 — Fresh-batch proof at trade grain

### Implemented

- **Fixture batch** (real parallel run output) is stored at  
  `renaissance_v4/game_theory/docs/proof/d14_gc/fixture_batch/batch_parallel_results_v1.json`  
  (schema `batch_parallel_results_v1`, written by `run_scenarios_parallel` session logs).
- **Payload samples** (generated from the same builders as Flask):  
  - `docs/proof/d14_gc/sample_get_student_panel_runs_row.json` — one L1 row (`d14_run_row_v1` enrichment).  
  - `docs/proof/d14_gc/sample_get_student_panel_selected_run.json` — L2 selected-run payload (`grain`: `trade_id`, `slices` array).  
  - `docs/proof/d14_gc/sample_student_decision_record_v1.json` — placeholder note when **zero closed trades** in batch.  
  - `docs/proof/d14_gc/sample_carousel_trade_id_keys.json` — proves carousel index → `trade_id` mapping for the fixture job.
- **Regenerator:** `scripts/d14_gc_export_proof_payloads.py` — expands `memory_root/batch_scorecard.jsonl.template` to a machine-local `memory_root/batch_scorecard.jsonl` (gitignored), sets `PATTERN_GAME_MEMORY_ROOT`, rewrites samples.

### API routes (Flask)

| Payload | Route |
|---------|--------|
| Run list | `GET /api/student-panel/runs?limit=50` |
| Selected run | `GET /api/student-panel/run/<job_id>/decisions` |
| Deep dive | `GET /api/student-panel/decision?job_id=<job_id>&trade_id=<trade_id>` |

Fixture `job_id`: **`d14_gc_fixture_job`** (see template).

### HTTP 200

- **Automated:** `renaissance_v4/game_theory/tests/test_d14_gap_closure_regression_v1.py` — `test_pattern_game_index_http_200`, `test_student_panel_runs_route_returns_d14_schema`.
- **Live server:** `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:<port>/` → `200` when Pattern Game Flask is running.

### True data constraint (non-fabricated)

The checked-in SQLite developer dataset has **~60 SOLUSDT bars**. Baseline replay in the fixture batch produced **0 closed trades** (`replay_outcomes_json: []`). Therefore **`student_decision_record_v1` for a real `trade_id` cannot be produced from this batch** without inventing data.

**Still open:** A full L3 JSON sample tied to a real engine `trade_id` requires a run where replay closes ≥1 trade (longer history DB or a manifest/scenario that trades on available bars). Until then, L3 proof is: **contract tests** + **`data_gap` honesty** (GC.4).

---

## GC.3 — Row delete wired to `DELETE /api/batch-scorecard/run/<job_id>`

### Implemented

- L1 table **last column ×** calls `DELETE` with JSON `{ "confirm": true }`, `stopPropagation` on the button, in-flight rows disabled (`web_app.py` JS in `refreshStudentPanelD11`).
- Server: `web_app.api_batch_scorecard_delete_run` — removes **scorecard line(s) only**; response includes **`groundhog_unchanged`** and **`student_proctor_learning_store_unchanged`**.

### Proof artifacts

| Claim | Evidence |
|--------|-----------|
| API contract | `test_batch_scorecard_delete_returns_groundhog_unchanged` |
| UI wiring | Source inspection: `pg-student-d11-row-del`, `confirm(...)` then `fetch('/api/batch-scorecard/run/'...)"` |

### Screenshots (operator)

- × control on a completed row; confirm dialog text stating Groundhog unchanged; row absent after success (attach under `docs/proof/d14_gc/screenshots/` if desired).

### Groundhog unchanged

- API response flags + test mock on `remove_batch_scorecard_line_by_job_id` — no call to `reset_pattern_game_engine_learning_state_v1` from this route.

---

## GC.4 — True data gaps remain explicit

### Implemented

- `build_student_decision_record_v1` uses string **`data_gap`** for missing exports; extends **`data_gaps`** with structured reasons (`student_panel_d14.py`).
- **Tests:** `test_build_student_decision_record_structured_reasoning_fields_are_data_gap` — all six D14-5 placeholders `data_gap`; `structured_reasoning_export_not_wired` in `data_gaps`.

### Deep-dive sample

With a batch that has trades, the deep-dive UI lists `data_gaps` from the record and does not substitute aggregates into baseline / reasoning fields.

### Open until export

- Per-trade baseline fields  
- Full decision-time rich context not in `OutcomeRecord` metadata  
- Per-trade Groundhog attribution in multi-trade runs  
- Structured reasoning (D14-5)  
- Pattern evaluation per trade  

---

## GC.5 — Structured reasoning plan (no fake reasoning)

### Document

- **`renaissance_v4/game_theory/docs/D14_structured_reasoning_implementation_plan_v1.md`** — field-by-field source path, exportable vs generatable vs instrumentation, immediate vs pipeline work.

---

## GC.6 — Proof doc (this file) + companion artifacts

| Area | Implemented this pass | Artifact | Still open | Why |
|------|------------------------|----------|------------|-----|
| GC.1 UI | Operator/D14 shell, dev seam split | tests + `web_app.py` | Screenshots optional | Browser-only |
| GC.2 APIs | Fixtures + samples + script | `docs/proof/d14_gc/*`, `scripts/d14_gc_export_proof_payloads.py` | Full `student_decision_record` with real `trade_id` | 60-bar DB → 0 trades |
| GC.3 delete | × + confirm + DELETE | tests + JS | — | — |
| GC.4 gaps | `data_gap` + tests | `student_panel_d14.py`, tests | Exports | No guessing |
| GC.5 plan | Planning doc only | `D14_structured_reasoning_implementation_plan_v1.md` | Implementation | Waits on instrumentation |
| GC.7 tests | Regression file | `test_d14_gap_closure_regression_v1.py` | — | — |

---

## GC.7 — Regression protection

### Test module

`renaissance_v4/game_theory/tests/test_d14_gap_closure_regression_v1.py`

| Test | Proves |
|------|--------|
| `test_operator_student_triangle_body_has_only_l1_l2_l3_shell` | No orphan seam/learn IDs between Student body and dev dock |
| `test_level1_render_fn_contains_run_table_only_no_handoff_dom` | L1 refresh has no D09/seam injection |
| `test_selected_run_api_missing_job_is_explicit` | No fake “grain” on error |
| `test_d13_selected_run_slices_keyed_by_trade_id_from_batch` | L2 slices keyed by `trade_id` |
| `test_build_student_decision_record_structured_reasoning_fields_are_data_gap` | Reasoning placeholders stay `data_gap` |
| `test_pattern_game_index_http_200` | Shell HTTP 200 |
| `test_batch_scorecard_delete_returns_groundhog_unchanged` | Delete path scorecard-only |
| `test_student_panel_runs_route_returns_d14_schema` | L1 API schema |
| `test_fixture_export_script_outputs_exist` | Committed JSON fixtures present |

Run:  
`PYTHONPATH=. python3 -m pytest renaissance_v4/game_theory/tests/test_d14_gap_closure_regression_v1.py -q`

---

## Related docs

- Architecture: `docs/D14_student_panel_architecture_spec_v1.md` (if present)  
- Field sources: `docs/D14_student_decision_record_v1_field_sources.md` (if present)  
- Curriculum: `docs/D13_student_panel_curriculum_v1.md`

---

## §F — Closeout commands

Performed in-repo:

1. `git add .` and `git commit -m "D14 gap closure — UI cleanup, fresh-batch proof, row delete wiring"`
2. `git pull origin main`
3. `git push origin main`

**Services:** Restart Pattern Game Flask (and any Docker stacks your deployment uses) after pull so the operator UI matches **`PATTERN_GAME_WEB_UI_VERSION`** in `web_app.py`.

**Verification checklist**

- [ ] `pytest …test_d14_gap_closure_regression_v1.py` — all passed  
- [ ] `python3 scripts/d14_gc_export_proof_payloads.py` — regenerates proof JSON  
- [ ] Live `GET /` and Student API routes return **200**
