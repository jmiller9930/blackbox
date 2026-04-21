# student_data_capability_audit_v1

**Purpose:** D12.B mandatory inventory — what exists, where, at what granularity, and what is missing.  
**Scope:** Codebase as of audit creation (`student_proctor`, `game_theory` replay/scorecard/panel paths).  
**Rule:** Statements below are grounded in named modules; “not exposed” means no stable public API in this repo inventory was found.

---

## Critical questions (explicit answers)

| # | Question | Answer |
|---|----------|--------|
| 1 | Can we tie Student store entries to a specific **decision** (parallel scenario id)? | **NO** for a first-class field. `student_learning_record_v1` requires `run_id`, `graded_unit_id` (closed trade), `context_signature_v1`, embedded `student_output_v1` (`renaissance_v4/game_theory/student_proctor/contracts_v1.py` `validate_student_learning_record_v1`). Listing by parallel scenario id is **not** implemented in `student_learning_store_v1.py` (only `list_student_learning_records_by_run_id`, `by_graded_unit_id`, `by_signature_key`). Scenario id ≠ `graded_unit_id` unless operationally made equal. |
| 2 | Can we compute **decision_changed_flag** per decision today? | **NO**. No field is written in batch/scenario/run_record that compares shadow Student vs baseline for that scenario. D11 exposes `decision_changed_gap: not_wired` (`student_panel_d11.py` slice + `build_student_decision_record_v1` baseline stubs). |
| 3 | Can we reconstruct **full context at decision time** (OHLC, indicators, classifications) from persisted artifacts alone? | **PARTIAL**. `run_record.json` may carry `indicator_context_quality`, `learning_memory_evidence`, optional `learning_run_audit_v1` (`run_memory.build_run_memory_record`). Structured OHLC/EMA/RSI/ATR/volume as a normalized “decision-time snapshot” is **not** a single guaranteed schema on `run_record`; `student_context_annex_v1` buckets exist in contracts but are not shown as always persisted to disk per scenario in this audit path. |
| 4 | Can we isolate **Groundhog influence per decision**? | **PARTIAL**. Per-scenario: `flatten_scenario_for_api` / `run_record` → `memory_applied`, `groundhog_mode`, `learning_memory_evidence` (`scorecard_drill.py`). Per-decision-window granularity inside a scenario would require worker/replay artifacts not consolidated here as a stable “per bar/window” row for the panel API. |
| 5 | Where does the pipeline **lose granularity** (run → scenario → decision)? | **Run:** `batch_scorecard.jsonl` one line per parallel **job** with aggregated metrics (`batch_scorecard.py`). **Scenario:** session log batch folder + per-folder `run_record.json` + README table (`scorecard_drill.build_scenario_list_for_batch`). **Decision/trade:** contracts center on `graded_unit_id` = closed trade (`contracts_v1.GRADED_UNIT_TYPE_V1`); parallel **scenario** is coarser than **trade** when one scenario contains many trades. **Student store** keys by `run_id` + trade/signature, not by `scenario_id`. |

---

## DECISION DATA

### student_action

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | SCENARIO (proxy) | `student_panel_d11.build_student_decision_record_v1`: `action` from `referee.trades` (ENTER vs NO_TRADE), not from `student_output_v1.act` | API `GET /api/student-panel/decision` | derived | True **student** action lives in `student_output_v1.act` when Proctor emits (`contracts_v1.py`); D11 path audited does **not** load `student_output` from `run_record` for this field. |

### student_direction

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | SCENARIO | Same builder: `_ref_direction_from_labels` on `operator_labels` from flattened scenario | API as above | derived | Not `student_output_v1.direction` unless separately wired into run_record/store. |

### student_confidence

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | DECISION (in contract) / NO in D11 panel | `student_output_v1.confidence_01` when record exists (`contracts_v1.validate_student_output_v1`); D11 sets `confidence: None` + `confidence_not_in_run_record` gap (`student_panel_d11.py`) | Store JSONL via `student_learning_record_v1`; API panel returns null confidence | authoritative in store when present; **absent** in D11 drilldown today | Slice API: `confidence_gap: not_exported` (`_slice_from_flat_scenario`). |

---

## BASELINE DATA

### baseline_action / baseline_direction / baseline_confidence

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| NO (as first-class fields) | — | No dedicated baseline triple persisted for A/B at scenario level in audited paths | not exposed | — | `baseline_comparison` in D11 is placeholders (`baseline_decision: "—"`, `changed: "—"`). `build_decision_audit` describes memory bundle vs manifest, not a Student baseline opponent (`run_memory.py`). |

### decision_changed_flag

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| NO | — | Not computed anywhere in scorecard or `run_record` builder | D11 marks `decision_changed_gap: not_wired` | — | No inference — UI shows gap. |

---

## CONTEXT DATA

### price (OHLC)

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | SCENARIO / RUN | Replay outputs / summaries; `run_record.referee` / `summary` paths; not a single OHLC series field in `build_student_decision_record_v1` | file (`run_record.json`); API batch-detail flatten | derived / raw mix | D11 exposes `context.price` as `summary.average_pnl` (mislabeled as “price” in structure — **average_pnl**, not OHLC) in `student_panel_d11.py`. |

### EMA / RSI / ATR / volume

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | SCENARIO | `indicator_context` in scenario/agent paths; `indicator_context_quality` on run_record (`scorecard_drill.flatten_scenario_for_api`) | file + API | derived | No guarantee all four indicators appear on every `run_record`. |

### trend / volatility / structure classification

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | SCENARIO | `student_context_annex_v1` optional buckets (`structure_context`, etc.) in `contracts_v1`; `icq` / narrative in run_record | file / validation only | derived | Optional annex not proven always written to session `run_record.json` for every scenario in this audit. |

---

## GROUNDHOG / MEMORY

### retrieval_count

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | RUN (aggregated) / SCENARIO (audit) | Scorecard: `student_retrieval_matches`, `recall_matches` (`batch_scorecard` rollups); `learning_run_audit_v1.recall_match_windows_total` per scenario when audit exists | scorecard file; parallel result → `aggregate_batch_learning_run_audit_v1` | derived | D11 `groundhog.retrieval_count` is **null** in decision record (`build_student_decision_record_v1`). |

### memory_used_flag

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | SCENARIO | `flatten_scenario_for_api` `memory_applied`; `learning_run_audit_v1.memory_bundle_applied` when present | file, API | authoritative when written | |

### context_used_flag

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | SCENARIO | Overlaps memory + Groundhog env flags in LME / audit | file | derived | No single boolean named `context_used` in audited panel code. |

### retrieved_records (any form)

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | SCENARIO / RUN | Audit lists counts (`recall_match_records_total`); not full record dump in scorecard line | replay audit JSON | derived | |

### influence description

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | SCENARIO | `learning_memory_evidence.narrative` / `operator_note` on run_record; audit `memory_operator_note_v1` | file | derived | D11 surfaces LME narrative in `groundhog.summary_of_influence`. |

---

## REFEREE DATA

### actual_trade

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | SCENARIO | `run_record.referee.trades` | file `run_record.json`; API D11 | authoritative | |

### outcome (WIN / LOSS / NO_TRADE)

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | SCENARIO | `referee_session` via `flatten` / `_slice_from_flat_scenario` | file + API | authoritative | |

### pnl

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | SCENARIO | `referee.cumulative_pnl` etc. | file + API | authoritative | |

---

## PERFORMANCE DATA

### win/loss classification per scenario

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | SCENARIO | `referee_session` + trade counts drive WIN/LOSS/NO_TRADE in D11 slice | API + file | authoritative | |

### per-trade pnl

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| PARTIAL | DECISION (trade) | `OutcomeRecord` ledger / `referee_truth_v1.pnl` in reveal path | engine / reveal artifacts | authoritative per trade | Scenario-level `run_record` may aggregate; per-trade needs ledger or `graded_unit_id` join — **not** exposed as a flat list in D11 API. |

### avg win / avg loss / expectancy

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | RUN / SCENARIO | `compute_pattern_outcome_quality_v1` from outcomes (`pattern_outcome_quality_v1.py`); batch rollup `expectancy_per_trade` on scorecard (`batch_scorecard`, `student_panel_d11` rows) | scorecard file; API `/api/student-panel/runs` | derived | Batch-level expectancy is **derived**; scenario may carry summary nested in worker result. |

---

## RUN-LEVEL AGGREGATES

### scorecard metrics

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | RUN | `read_batch_scorecard_recent`, `record_parallel_batch_finished` (`batch_scorecard.py`) | file `batch_scorecard.jsonl` | authoritative for recorded line | |

### batch rollups

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | RUN | `compute_batch_score_percentages`, learning rollups + MCI (`learning_run_audit`, `batch_scorecard`) | file + in-memory inflight merge in `web_app._merge_scorecard_with_inflight` | derived | |

### harness / handoff deltas

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| YES | RUN | `student_panel_d11.build_d11_run_rows_v1` HB/SH/evidence objects from scorecard fields | API `GET /api/student-panel/runs` | derived | |

---

## STUDENT STORE

| Field | Value |
|-------|--------|
| **What is stored** | `student_learning_record_v1`: `record_id`, `created_utc`, `run_id`, `graded_unit_id`, `context_signature_v1`, embedded `student_output_v1`, `referee_outcome_subset`, `alignment_flags_v1` (`contracts_v1.validate_student_learning_record_v1`). |
| **Key structure** | **Required:** `run_id`, `graded_unit_id`, `context_signature_v1` (dict with `signature_key` used in `list_student_learning_records_by_signature_key`). |
| **Retrieval scope** | **RUN:** `list_student_learning_records_by_run_id`. **Graded unit:** `list_student_learning_records_by_graded_unit_id`. **Signature:** `list_student_learning_records_by_signature_key`. **Not:** parallel `scenario_id` / `decision_id` as primary key. |
| **Access** | File JSONL `default_student_learning_store_path_v1` (`student_learning_store_v1.py`); API read-only status `GET /api/student-proctor/learning-store`; D11 counts by `run_id` only. |

---

## Summary: EXISTS vs MISSING (D12-facing)

| Area | Exists | Missing / partial |
|------|--------|-------------------|
| Referee per scenario | yes (run_record + flatten) | — |
| Student shadow decision in panel | partial (often Referee-derived in D11) | true `student_output_v1` surfacing on drilldown |
| Baseline vs Student delta | no | baseline triple + `decision_changed_flag` |
| Full indicator/OHLC snapshot | partial | unified decision-time context package on disk |
| Groundhog per bar | partial (audit aggregates) | per-window row for panel |
| Store → scenario link | partial (trade/signature) | **scenario_id** index |
| Run aggregates | yes | — |

---

## Verification pointers (code)

- Contracts: `renaissance_v4/game_theory/student_proctor/contracts_v1.py`
- Store I/O: `renaissance_v4/game_theory/student_proctor/student_learning_store_v1.py`
- Run record shape: `renaissance_v4/game_theory/run_memory.py` `build_run_memory_record`
- Scenario list + flatten: `renaissance_v4/game_theory/scorecard_drill.py`
- Scorecard: `renaissance_v4/game_theory/batch_scorecard.py`
- Learning audit: `renaissance_v4/game_theory/learning_run_audit.py`
- D11 panel: `renaissance_v4/game_theory/student_panel_d11.py`
- Flask routes: `renaissance_v4/game_theory/web_app.py` `/api/student-panel/*`

---

*End student_data_capability_audit_v1*
