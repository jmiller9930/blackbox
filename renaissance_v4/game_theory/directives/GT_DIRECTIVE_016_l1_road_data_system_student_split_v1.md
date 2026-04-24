# GT_DIRECTIVE_016 — L1 road data: system vs Anna band + denormalized rollups

**Date:** 2026-04-24 (amended 2026-04-24 — **L1 road API slice** shipped)  
**Status:** **ACTIVE — v1 road slice SHIPPED** — `GET /api/student-panel/l1-road` + `student_panel_l1_road_v1` + tests + fixture + operator proof. **OPEN** for optional scorecard denorm at `record_parallel_batch_finished` (Anna align, mem/ctx flags) and embedded L1 **table** bands until accepted or deferred.  
**From:** Architect (via operator product lock)  
**To:** Engineer  
**CC:** Operator, Product, Referee, UI  
**Scope:** `renaissance_v4/game_theory` — `student_panel_l1_road_v1.py`, `web_app.py` (`GET /api/student-panel/l1-road`), tests/fixtures/proof; future: `student_panel_d11.py`, `student_panel_d14.py`, `GET /api/student-panel/runs` column bands, `batch_scorecard.py` denorm fields per §16.2 original text.

## Canonical workflow record

This file is the canonical record for this directive.

Workflow:

1. Architect issues directive here.
2. Engineer reads and performs work.
3. Engineer appends response below.
4. Operator notifies Architect to review this folder.
5. Architect appends acceptance or rework below.

## Fault

**Today:** L1 mixes **system trade-win %**, **harness (HB)**, and **Student handoff (SH)** without a **visual or semantic A | B split**. Anna-aligned rollups (e.g. `student_referee_direction_align_rate_percent`) exist in **L2** (`build_d13_selected_run_payload_v1`) but are **not** denormalized onto the scorecard line, so listing **N** runs cannot afford per-row D13 scans.

## Directive

### 16.1 L1 layout (operator contract)

Render **two adjacent bands** on the exam list row (group headers or sub-columns):

| Band | Purpose | Minimum columns (names may be UI labels) |
|------|---------|---------------------------------------------|
| **A — System** | Frozen ruler + this system sit | Window, `#tr`, `Sys%`, `Run%` (only when cold run executed this line; else honest empty or “= anchor”), `>BL`, `E/tr` as needed |
| **B — Anna** | Her sit + memory story | `#Anna`, **`Anna%`** (definition: **default** = `student_referee_direction_align_rate_percent` from current D13 math unless architect changes), win/loss counts optional, `Mem`, `Ctx`, `Hit` (retrieval count), `Fx` (loose learning flag per agreed boolean rule) |

**Rename / demote:** `HB` must not sit in band B without relabeling; either move to **A** footnote, **engine** strip, or map into **`Ctx`** with a documented rule. **`SH`** retires from opaque letters in favor of **`ExLog` / `Learn`** per operator glossary.

### 16.2 Denormalization (performance non-negotiable)

At **`record_parallel_batch_finished`** (or immediately after parallel completion in the same transaction as scorecard append), compute and persist **once** per `job_id`:

- `anna_align_rate_percent`, `anna_align_evaluable_trades`, `anna_align_matches` (or equivalent names)
- `anna_trade_count` (usually equals `batch_trades_count` when 1:1 graded)
- `mem_used_flag`, `ctx_used_flag` (same semantics as L2 `run_summary` today)
- `student_retrieval_matches` (already on line — ensure present)
- `fx_loose_learning_flag` (or name per schema) using the **documented** loose rule from operator sign-off

**Forbidden:** scanning the entire Student learning JSONL for **each** row of `GET /api/student-panel/runs`.

### 16.3 Legend + API

- L1 legend documents **every** abbreviated header (no mystery symbols).
- `GET /api/student-panel/runs` exposes new fields under `l1_columns_v1` semantics extension.

## Proof required

1. **Performance** — Benchmark or timed test: `/api/student-panel/runs?limit=50` does not open `batch_parallel_results` + full store **per row** on hot path.
2. **HTTP** — L1 API returns new fields; UI renders bands.
3. **Tests** — Regression on D11/D14 row builders + scorecard append shape.
4. **Doc** — `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §18.1 table row for L1 updated; **§18.4** tracks **GT_DIRECTIVE_016**.
5. **Closeout** — **§18.3 GT_DIRECTIVE_009** when `web_app.py` / panel modules change.

## Deficiencies log update

Log **GT_DIRECTIVE_016** until **Accepted**.

---

## Engineer update

**2026-04-24 — v1 L1 road API (BUILD brief)**

- **`student_panel_l1_road_v1.py`** — Single-pass read of `batch_scorecard.jsonl` (file order); group key `(fingerprint_sha256_40, student_brain_profile_v1, llm_model)`; **A \| B** vs oldest **baseline** row in the same fingerprint; `pass_rate_percent` = mean `referee_win_pct`; **E** = mean `expectancy_per_trade`; **P** = mean optional `student_l1_process_score_v1` when present (reserved field for future batch denorm — E-only A/B when absent); `legend` object for UI.  
- **`web_app.py`** — `GET /api/student-panel/l1-road` → **200**; `PATTERN_GAME_WEB_UI_VERSION` bump.  
- **Tests** — `tests/test_gt_directive_016_l1_road_v1.py` (grouping, LLM split, aggregates, A/B, fingerprint isolation, empty structure, HTTP with `PATTERN_GAME_MEMORY_ROOT`).  
- **Fixture** — `tests/fixtures/gt_directive_016_l1_road_scorecard_lines.json`.  
- **Proof** — `docs/proof/exam_v1/GT_DIRECTIVE_016_operator_proof_l1_road_v1.md` + `GT_DIRECTIVE_016_operator_proof_l1_road_response_v1.json`.  
- **Not in this slice:** L3 wiring; new Referee grading; scorecard append-time Anna-align denorm (original §16.2); embedded L1 row **A \| B** column UI (consume `l1-road` next).

---

## Architect review

**Status:** pending architect review (v1 road API slice — proof in repo)
