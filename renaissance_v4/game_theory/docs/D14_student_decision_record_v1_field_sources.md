# P1 — `student_decision_record_v1` field sources (D14-1)

Authoritative builder: `renaissance_v4/game_theory/student_panel_d14.py` → `build_student_decision_record_v1`.

Legend: **Student** = Proctor learning store / `student_output_v1`; **Referee** = `OutcomeRecord` JSON in `replay_outcomes_json`; **Meta** = `OutcomeRecord.metadata` when present; **gap** = explicit `data_gap` string.

| Field | Source |
|-------|--------|
| `run_id` | Scorecard / request |
| `trade_id`, `graded_unit_id` | Referee outcome JSON / graded unit (same id for trade grain) |
| `scenario_id` | Parallel worker result row |
| `timestamp_utc` | `OutcomeRecord.entry_time` (ms → UTC ISO) |
| `symbol` | Referee outcome |
| `timeframe` | Meta or `run_record` echo — else `data_gap` |
| `student_action` | `student_output.act` → ENTER / NO_TRADE — else `data_gap` |
| `student_direction`, `student_confidence_01` | Student store `student_output` — else `data_gap` |
| `student_confidence_band`, `student_action_v1`, `student_supporting_indicators`, `student_conflicting_indicators`, `student_context_fit`, `student_invalidation_text`, `student_reasoning_text` | Student store `student_output` thesis keys — else `data_gap` (lists must be JSON arrays on the stored object) |
| `data_gaps` (thesis) | For `student_brain_profile_v1` = `memory_context_llm_student`: `student_directional_thesis_store_missing_for_llm_profile_v1` / `student_directional_thesis_incomplete_for_llm_profile_v1` when the stored `student_output` lacks a complete thesis (precondition for **GT_DIRECTIVE_017**) |
| `baseline_*`, `decision_changed_flag` | **gap** until per-trade baseline export exists |
| `price_open/high/low/close` | Meta `ohlc` dict — else `data_gap` |
| `ema_fast`, `ema_slow`, `rsi_14`, `atr_14`, `volume`, `trend_state`, `volatility_regime`, `structure_state` | Meta / aliased keys — else `data_gap` |
| `groundhog_used_flag`, `context_used_flag`, `memory_used_flag`, `retrieval_count`, `retrieval_signature_key`, `influence_summary` | Student store row — honest flags; counts may be `data_gap` |
| `pattern_*` | **gap** until per-trade pattern export |
| `referee_*`, `is_win`, `is_loss` | Referee outcome only |
| `structured_reasoning_v1` | **gap** until D14-5 export path exists |

**L2 carousel slice (`student_panel_trade_slice_v1`, `student_panel_d13.py`):** In addition to the table above at L3 grain, L2 tiles include **`referee_direction`** (from `replay_outcomes_json.direction`), **`student_referee_direction_align`** (`True` / `False` / `data_gap` — compares **Student store** `student_output.direction` to referee direction only), and run-level rollups `student_referee_direction_align_*` on **`run_summary`** (**GT_DIRECTIVE_009a**, **§18.4** of `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`).
