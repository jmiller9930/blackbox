# D14 — Canonical architecture spec (Student panel, trade grain, reasoning)

**Status:** engineering contract. Implementation proof lives in `D14_student_panel_gap_closure_proof.md`.  
**Field mapping (P1):** `D14_student_decision_record_v1_field_sources.md`.

---

## 0. Architectural intent (locked)

- **Mode:** Forced trade. Each learning run is an exam; each **trade opportunity** is one evaluated interaction.
- **Hierarchy:** L1 run table → L2 single panel (run summary band + trade carousel) → L3 one trade deep dive. No mixed-level rendering.
- **Grain:** **Trade grain** — slice identity = **`trade_id`** (and **`graded_unit_id`** with same value). **`scenario_id`** is provenance metadata only.
- **Truth domains (no substitution):** Student truth, Referee truth, Groundhog truth, Baseline truth.

---

## D14-1 — `student_decision_record_v1`

Single authoritative per-trade object for the API/UI. All required flat fields are listed in the proof mapping doc; missing lineage returns the string **`data_gap`**.

**Proof:** P1 field map, P2 automated separation tests, P3 sample payload from a fresh batch.

---

## D14-2 — Level 1 run table

One row per exam run; required aggregates and Groundhog state **COLD|WEAK|ACTIVE|STRONG** per spec.  
Implementation: `build_d11_run_rows_v1` + `enrich_student_panel_run_rows_d14` (`student_panel_d14.py`).

**Proof:** P4 API artifact, P5 tests on aggregates + Groundhog rules.

---

## D14-3 — Level 2 selected-run panel

One horizontal **run summary band** + **trade carousel** (never separate panels). Carousel cards keyed by **`trade_id`** with D14 card field names.

**Proof:** P6 UI/API evidence, P7 tests (carousel key).

---

## D14-4 — Level 3 deep dive

Full trade inspection; **recorded truth only**; **`data_gap`** for missing exports.

**Proof:** P8 UI/API evidence, P9 tests (`trade_id` load, section separation).

---

## D14-5 — Structured reasoning export

Bounded `structured_reasoning_v1` block (not chain-of-thought). Currently **placeholder `data_gap`** until exporter is wired.

**Proof:** P10 sample, P11 tests.

---

## D14-6 — History vs Groundhog controls

- **Delete/archive one run:** `DELETE /api/batch-scorecard/run/<job_id>` with JSON `{"confirm": true}` — scorecard JSONL lines for that `job_id` only; **does not** change Groundhog or engine learning.
- **Groundhog / engine reset:** existing `POST /api/pattern-game/reset-learning` (separate).
- **Combined operator action:** invoke both explicitly; no automatic pairing.

**Proof:** P12 UI, P13 scripted independence tests.

---

## §7 Accepted gaps

Must remain explicit **`data_gap`** (not hidden): per-trade baseline, multi-trade Groundhog attribution, rich decision-time context, structured reasoning, per-trade pattern evaluation — until dedicated exports land.

---

## §8–10 Proof register, test coverage, closure rule

See `D14_student_panel_gap_closure_proof.md`. D14 closes only when proofs exist and gaps are honest.

---

## §F Operational closeout

Per pass: commit, `git pull origin main`, `git push origin main`, restart Flask/Docker as applicable, update proof doc + version (`PATTERN_GAME_WEB_UI_VERSION` in `web_app.py`).
