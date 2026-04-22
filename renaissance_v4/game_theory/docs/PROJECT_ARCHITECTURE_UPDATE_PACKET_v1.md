# Project architecture update packet (v1)

**Audience:** product + engineering. **Scope:** Student panel, batch/scorecard, Groundhog, truth domains.  
**Companion contracts:** `D14_student_panel_architecture_spec_v1.md`, `D13_student_panel_curriculum_v1.md`, `D14_student_decision_record_v1_field_sources.md`, `D14_student_panel_gap_closure_proof.md`.

---

## 1. Executive architecture directive

### What changed in the product model

- **Two truths are first-class:** **moment truth** (what the learner should judge at a decision instant) and **execution truth** (what the Referee actually scored for a completed interaction).
- **Two grains are first-class:** **trade-grain** (one closed trade / graded unit) and **scenario-grain** (batch harness row: manifest + `scenario_id`).
- **Groundhog** is named explicitly as the **context + memory** lane that can influence behavior; it is **not** the same object as the Referee ledger.

### What is now canonical (vocabulary)

| Term | Meaning |
|------|---------|
| **Run** | One **exam** execution: a batch job the scorecard indexes by **`job_id`**. UI and APIs treat **run ≡ exam** for Student panel purposes. |
| **Slice** | One **trade opportunity** in the curriculum UI: carousel + L3 deep dive identity = **`trade_id`** (see §5). Not `scenario_id`. |
| **Groundhog** | **Context + memory**: retrieval, learning-store rows, harness flags that D11/D13/D14 aggregate into run- and slice-level signals. |
| **Moment truth** | Decision-time teaching payload: frame, visible state, gates / policy, **expected** action. *Export contract for Level 0 is aspirational — see §4.* |
| **Execution truth** | Post-hoc **audit** payload: actual trade, outcome, PnL, Referee fields. **`student_decision_record_v1`** is the coded contract for L3. |

### What engineering must stop doing

1. **Stop keying the carousel or L3 loader on `scenario_id`** when multiple trades can exist under one scenario row.
2. **Stop substituting** Referee facts with Student narrative, or Student intent with Referee outcome, without labeling the domain.
3. **Stop inventing** baseline deltas, per-trade pattern scores, rich OHLC/context, or structured reasoning **strings** when exporters do not exist — use the literal string **`data_gap`** (and structured `data_gaps` reasons where implemented).
4. **Stop implying** “memory caused this PnL” from trade-only rows unless **paired instrumentation** or explicit attribution fields exist (see gap matrix).
5. **Stop mixing UI levels** in one view (e.g. run table inside deep dive) without a deliberate spec — L1/L2/L3 separation remains mandatory for the shipped Student panel.

---

## 2. Canonical system model

### A. Moment truth / decision teaching

- **Decision frame:** bounded time/price context the policy evaluates (e.g. bar window, attention region).
- **What the learner saw:** chart/state snapshot or equivalent **at the frame**, not post-trade summary alone.
- **Gates / policy conditions:** boolean or enumerated **predicates** (e.g. NO_TRADE allowed, regime filter).
- **Expected action:** rubric-scored **should / should-not** at that frame (may differ from what the agent later did in execution).

**Purpose:** pedagogy, exams, “why from the student’s perspective.”

### B. Execution truth / trade definition

- **Actual trade:** open/close lifecycle the engine + Referee graded.
- **Outcome / PnL:** `OutcomeRecord` lineage in `replay_outcomes_json`.
- **Audit truth:** immutable alignment fields (`trade_id`, `graded_unit_id`, `scenario_id` provenance, timestamps).

**Purpose:** accountability, receipts, alignment checks.

### C. Learning layer

- **Groundhog updates:** scorecard + batch telemetry + learning store signals (D14 run row enrichment, carousel `groundhog_usage_label` heuristics).
- **What is remembered:** `student_learning_store_v1` rows keyed by **`graded_unit_id`** (trade grain).
- **What influences future behavior:** append-only learning rows, retrieval matches, harness handoff flags — aggregated honestly at run level; **per-trade multi-hop attribution** remains largely **open** (see §6).

### How the three connect

```text
Moment truth (frame_id) ----may reference----> scenario_id / manifest / tape position
        |                                              |
        v                                              v
Execution truth (trade_id) <----graded when---- Referee closes trade
        ^
        |
Learning layer (Groundhog + store) ----feeds---- next run's context/memory signals
```

**Join rule (when both exist):** a **moment** record SHOULD carry optional **`trade_id`** / **`run_id`** links; a **trade** record carries **`scenario_id`** and optional **moment** anchors when export exists. **Until `decision_frame_v1` is implemented, moment truth is not a coded API object** — do not pretend L3 carries full frame state.

---

## 3. UI architecture spec

### Level 1 — Run table

- **Surface:** `GET /api/student-panel/runs`.
- **Grain:** one row per **run (exam)** / `job_id`.
- **Shows:** aggregates, pattern/evaluation labels, D14 enrichment (`d14_run_row_v1` block when present).

### Level 2 — Selected-run panel

- **Surface:** `GET /api/student-panel/run/<job_id>/decisions`.
- **Payload schema:** `student_panel_d13_selected_run_v1`.
- **Layout (mandatory):** single panel with:
  - **Run summary band** (`run_summary`)
  - **Trade carousel** (`slices[]`) — one card per **trade opportunity** (`trade_id`)

### Level 3 — Deep dive

- **Surface:** `GET /api/student-panel/decision?job_id=&trade_id=` (`decision_id=` accepted as **migration alias only**).
- **Payload schema:** `student_decision_record_v1`.
- **Shows:** Student vs Referee vs baseline placeholders vs context/memory flags — **recorded truth + explicit gaps**.

### Level 0 / companion (future) — Decision frame / exam card

- **Intent:** full-screen or side **moment truth** viewer: frame, learner-visible state, gates, **expected** action, optional link to the **slice** (`trade_id`) if the frame resolved to a trade.
- **Status:** **not implemented** as a first-class API in v1 packet; engineering must **not** overload `student_decision_record_v1` to mean “exam card” without a separate `decision_frame_v1` (or equivalent) spec and proofs.

---

## 4. Data contract spec (engineering codes from this)

### Global rules

- **Missing lineage:** string value **`data_gap`** on scalar fields in `student_decision_record_v1` where the field map says so; array `data_gaps` on selected-run payload when batch artifacts are missing.
- **Prohibited substitutions:** no silent default to “neutral” confidence, no fabricated OHLC, no inferred baseline comparison as numeric truth.

### Object: `student_decision_record_v1`

- **Builder:** `student_panel_d14.build_student_decision_record_v1`.
- **Authority table:** `D14_student_decision_record_v1_field_sources.md` — **source of truth per field** is listed there; this packet does not duplicate every column.
- **Hard keys:** `run_id`, `trade_id`, `graded_unit_id` (same value as `trade_id` for trade grain), `scenario_id` (provenance).

### Object: `student_panel_d13_selected_run_v1`

- **Builder:** `student_panel_d13.build_d13_selected_run_payload_v1`.
- **Top-level:** `ok`, `schema`, `run_id`, `run_summary`, `slices`, `slice_ordering`, `grain` (`"trade_id"`), `scenario_list_error`, `data_gaps`, `note`.

### Object: `student_panel_trade_slice_v1` (carousel slice)

- **Embedded in:** `slices[]` above.
- **Keys include:** `schema`, `trade_id`, `graded_unit_id`, `timestamp_utc`, `student_direction`, `student_confidence_01`, `referee_outcome`, `groundhog_usage_label`, `decision_changed_flag`, display aliases (`direction`, `confidence`, `result`, `groundhog_usage`), `order_index`.

### Object: run summary band (`run_summary` object)

- **Not a separate schema constant** — object inside `student_panel_d13_selected_run_v1` with `run_id`, aggregates (`total_trade_opportunities`, win/loss counts, rates, expectancy), `behavior_changed_flag`, `outcome_improved_flag`, `groundhog_state` (`COLD|WEAK|ACTIVE|STRONG`), `context_used_flag`, `memory_used_flag`, `panel_run_row_schema`.

### Object: `decision_frame_v1` (specified, not shipped)

**Purpose:** moment truth for Level 0. **Minimum suggested fields** (to be frozen when implemented):

| Field | Role |
|-------|------|
| `schema` | `"decision_frame_v1"` |
| `frame_id` | Canonical stable id for this frame within a run |
| `run_id` | Parent exam |
| `scenario_id` | Harness row |
| `trade_id` | Optional — if frame is tied to a known trade |
| `window_start_utc`, `window_end_utc` | Decision interval |
| `learner_visible_state` | Serialized snapshot or hash + retrieval key |
| `gates` | List of { `name`, `passed`, `value` } |
| `expected_action` | Rubric label |
| `policy_version` | Which rulepack |

**Allowed `data_gap`:** any subfield not yet instrumented.  
**Prohibited:** embedding full chain-of-thought; use bounded `structured_reasoning_v1` policy from D14 spec when wired.

### L1 row enrichment: `d14_run_row_v1`

- **Attached by:** `enrich_student_panel_run_rows_d14` to run table rows.
- **Source:** `batch_parallel_results_v1.json` when present; else honest degradation per D14.

---

## 5. Identity and keying rules

| Concept | Canonical key | Notes |
|---------|----------------|-------|
| **Run (exam)** | **`job_id`** in HTTP routes and scorecard index | Payloads also use **`run_id`**; for Student panel builders they refer to the **same** run. |
| **Trade / slice** | **`trade_id`** | Carousel order index is **not** a stable id. |
| **Graded unit** | **`graded_unit_id`** | For **closed trade** curriculum: **must equal `trade_id`** (D14). |
| **Scenario / harness row** | **`scenario_id`** | Batch manifest row; **may contain 0..N trades** in `replay_outcomes_json`. |

**UI key usage**

| Level | Primary selector |
|-------|------------------|
| L1 | `job_id` (row click) |
| L2 | `job_id` → load `slices[].trade_id` for carousel |
| L3 | `job_id` + `trade_id` (query params) |
| L0 (future) | `run_id` + `frame_id` (proposed) |

**Relation summary:** `scenario_id` groups tape/config; **`trade_id`** is the **only** valid carousel/L3 identity for multi-trade scenarios. `graded_unit_id` aliases `trade_id` for this product mode.

---

## 6. Gap closure matrix

| Capability | Already present | Exportable now | Generatable now (fixtures) | Needs new instrumentation |
|------------|-----------------|----------------|----------------------------|---------------------------|
| Run table + D14 run band | ✓ | ✓ | ✓ | — |
| L2 carousel keyed by `trade_id` | ✓ | ✓ | ✓ (see `docs/proof/d14_gc/`) | — |
| L3 `student_decision_record_v1` | ✓ | ✓ when batch has closed trades | ✓ | Rich meta OHLC / indicators |
| `batch_parallel_results_v1` trade enumeration | ✓ when batch logged | ✓ | ✓ | Older batches: re-run |
| Per-trade baseline fields | Honest `data_gap` | Partial | Tests | Per-trade baseline exporter |
| `structured_reasoning_v1` | Placeholder `data_gap` | — | — | Bounded exporter (D14-5) |
| Multi-trade Groundhog attribution | Run-level + heuristics | — | — | Per-trade memory causality design |
| **`decision_frame_v1` / Level 0** | — | — | Partial (manual JSON) | Frame capture pipeline + API |

---

## 7. Proof and acceptance

Each vertical slice should ship with **numbered** evidence. Minimum bar (aligned with D14 proof register):

| Item | Code paths | Tests | Sample payloads | UI / HTTP |
|------|------------|-------|------------------|-----------|
| L1 | `web_app` student-panel runs + `enrich_student_panel_run_rows_d14` | D14 aggregate / Groundhog tests | `sample_get_student_panel_runs_row.json` | Screenshot or `200` capture |
| L2 | `build_d13_selected_run_payload_v1` | `test_d13_selected_run_slices_keyed_by_trade_id_from_batch`, `test_trade_id_is_carousel_and_api_key` | `sample_get_student_panel_selected_run.json`, `proof_api_selected_run_with_slices.json` | Screenshot L2 |
| L3 | `build_student_decision_record_v1` | D14 contract tests | `proof_api_deep_dive.json`, `sample_student_decision_record_v1.json` | Screenshot L3 |
| Honesty | — | `data_gap` / `data_gaps` tests | Fixture with empty trades | Shows gaps in UI |
| Deploy | — | — | — | `GET` returns **200** on deployed host for proof `job_id`s |

**Version pin:** update `PATTERN_GAME_WEB_UI_VERSION` in `web_app.py` when UI proof changes per D14 §F.

---

## 8. Operational closeout (every merge that touches this surface)

1. Commit locally with a message that states **which truth domain** or UI level changed.  
2. `git pull` (remote default branch).  
3. `git push` to origin.  
4. Restart **Flask** (`web_app`) and any **Docker** sidecars that cache scorecard or batch paths.  
5. Verify routes: `GET /api/student-panel/runs`, `GET /api/student-panel/run/<job_id>/decisions`, `GET /api/student-panel/decision?job_id=&trade_id=`.  
6. Spot-check UI: L1 row → L2 band+carousel → L3 deep dive.

---

## 9. Revision history

| Version | Date | Summary |
|---------|------|---------|
| v1 | 2026-04-21 | Initial packet: run≡exam, slice≡trade opportunity, Groundhog=context+memory, moment vs execution truth, L0 future `decision_frame_v1`, keying rules, data contracts pointing at D13/D14 builders and proof folder. |

**Prior art folded in:** D13 curriculum (trade grain), D14 architecture spec + field sources + gap closure proof, `CLOSED_TRADE_BATCH_README.md` for operator-visible batch proof.
