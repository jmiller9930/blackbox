# GT_DIRECTIVE_016 — L1 road data: system vs Anna band + denormalized rollups

**Date:** 2026-04-24 (amended 2026-04-24 — **L1 road API + L1 row UI merge** shipped; **v1 CLOSED** same day)  
**Status:** **Accepted v1 / CLOSED** — L1 road visible and usable: **`GET /api/student-panel/l1-road`**, **`l1_road_v1`** on **`GET /api/student-panel/runs`**, Level 1 columns + **API-driven legend**, tests + operator proof. **Remaining scope** from original §16.1/§16.2 text is **not undefined**; it is **transferred** to the **Deferred work register** below (named follow-ons). **GT_DIRECTIVE_017** is **unblocked**.  
**From:** Architect (via operator product lock)  
**To:** Engineer  
**CC:** Operator, Product, Referee, UI  
**Scope (016 v1 shipped):** `renaissance_v4/game_theory` — `student_panel_l1_road_v1.py` (`road_by_job_id_v1`, `member_job_ids`), `web_app.py` (`GET /api/student-panel/l1-road`, **`l1_road_v1` overlay on** `GET /api/student-panel/runs`, L1 table columns + legend from API); tests/fixtures/proof. **Follow-on:** `batch_scorecard.py` denorm + §16.1 dual-band → **016R1**; exam-pack E/P surfacing → **019** (see Deferred work register).

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

**Accepted v1 — 2026-04-24** — see Architect review (CLOSED + deferred register).

---

## Deferred work register (post-016 v1; no undefined gaps)

Original directive §16.1–§16.2 items **not** shipped in 016 v1 are **explicitly owned** by these follow-ons (identifiers reserved until architect files them):

| Gap | Named follow-on | Notes |
|-----|-----------------|-------|
| Scorecard-line denorm at parallel finish (Anna align %, mem/ctx flags, retrieval counts, `Fx` rule, §16.2) | **`GT_DIRECTIVE_016R1`** (reserved) — *file to be issued* | Performance contract unchanged: **no** per-row learning-store scan on `GET …/runs`. |
| Formal **A \| B** dual-band row chrome vs current single-table columns (§16.1) | **`GT_DIRECTIVE_016R1`** (same or split **016R2** at architect discretion) | UI polish; semantics already honest via Road / Anchor / gaps. |
| Exam-pack **E** / **P** on scorecard + L1 vs scorecard **expectancy** + optional **P** field | **`GT_DIRECTIVE_019`** (reserved) — *or product exam grading directive* | **015** already defers refine-then-seal / full pack parity on the parallel path; this is **persistence + surfacing**, not 016 regression. |

**Coupling:** **GT_DIRECTIVE_017** §17.x cross-ref on **L1 `Fx`** remains: strong **Fx** claims require L3 gap closure on architect-defined sample trades — implement when **016R1** defines `fx_loose_learning_flag` persistence.

---

## Engineer update

**2026-04-24 — v1 L1 road API (BUILD brief)**

- **`student_panel_l1_road_v1.py`** — Single-pass read of `batch_scorecard.jsonl` (file order); group key `(fingerprint_sha256_40, student_brain_profile_v1, llm_model)`; **A \| B** vs oldest **baseline** row in the same fingerprint; `pass_rate_percent` = mean `referee_win_pct`; **E** = mean `expectancy_per_trade`; **P** = mean optional `student_l1_process_score_v1` when present (reserved field for future batch denorm — E-only A/B when absent); `legend` object for UI.  
- **`web_app.py`** — `GET /api/student-panel/l1-road` → **200**; `PATTERN_GAME_WEB_UI_VERSION` bump.  
- **Tests** — `tests/test_gt_directive_016_l1_road_v1.py` (grouping, LLM split, aggregates, A/B, fingerprint isolation, empty structure, HTTP with `PATTERN_GAME_MEMORY_ROOT`).  
- **Fixture** — `tests/fixtures/gt_directive_016_l1_road_scorecard_lines.json`.  
- **Proof** — `docs/proof/exam_v1/GT_DIRECTIVE_016_operator_proof_l1_road_v1.md` + `GT_DIRECTIVE_016_operator_proof_l1_road_response_v1.json`.  
- **2026-04-24 (later)** — **`road_by_job_id_v1`** on L1 road payload; **`l1_road_v1`** overlay embedded on **`GET /api/student-panel/runs`**; Level 1 embedded table: **Profile**, **LLM**, **Road** (band), **Anchor** (Ruler / Anchor / vs anchor), **Road gaps** (group `data_gaps` + process P-compare flag); column **titles** use **`legend`** strings (not hardcoded semantics); legend block under table rendered from **`l1_road_v1.legend`**. `PATTERN_GAME_WEB_UI_VERSION` bump.  
- **Still not complete:** scorecard append-time denorm (Anna %, mem/ctx flags); exam-pack **E** vs scorecard expectancy; persisted **P** beyond optional `student_l1_process_score_v1`; formal **A \| B** dual-band row layout (§16.1) vs added columns.

---

## Architect review

### Partial acceptance — backend + L1 row integration (2026-04-24)

**Accepted:** `student_panel_l1_road_v1.py`; single-pass scorecard-only aggregation; grouping by fingerprint + brain profile + LLM model; Qwen vs DeepSeek split; baseline-anchored A/B per fingerprint; no cross-fingerprint mixing; no learning-store scans; honest `data_gaps` for missing baseline / process score; server-driven `legend`; `GET /api/student-panel/l1-road` **200**; fixture, operator proof, tests; commit / push / gsync; **`road_by_job_id_v1`**; **`l1_road_v1`** on **`GET /api/student-panel/runs`**; **Level 1 UI** shows profile, LLM (when applicable), band, anchor role, road gaps, and **legend text from API** (not copy-pasted definitions in JS).

**Deferred (written — not OPEN):** scorecard-line denorm (§16.2); **P** optional until denorm; **E** = scorecard expectancy until exam-pack surfacing (**019** or successor); §16.1 dual-band chrome — see **Deferred work register** above. **GT_DIRECTIVE_017** may proceed.

**One-line summary (closure):** **016 v1** delivers truthful L1 road data **and** embeds it in the Level 1 table with **server-driven legend**; all former “OPEN” gaps are **named** to **016R1** / **019** (reserved).

**Status:** **Accepted v1 / CLOSED** (2026-04-24)
