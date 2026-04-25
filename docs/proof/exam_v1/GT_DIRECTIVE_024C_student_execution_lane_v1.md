# GT_DIRECTIVE_024C — Student-controlled execution lane (proof)

**Status:** Implementation complete — separate Student lane + scorecard rollups + trace events; batch **parent** orchestration (workers unchanged for baseline).  
**Code:** `renaissance_v4/game_theory/student_controlled_replay_v1.py`, `renaissance_v4/research/replay_runner.py` (optional `student_execution_intent_v1` kwarg), `renaissance_v4/game_theory/parallel_runner.py`, `renaissance_v4/game_theory/batch_scorecard.py`, `renaissance_v4/game_theory/learning_trace_events_v1.py`

## Baseline replay unchanged

- Default **`run_manifest_replay(...)`** calls do not pass `student_execution_intent_v1`; the new parameter **defaults to `None`**, preserving the historical control path.
- Parallel workers still build **`out` from `control_replay`** as before; Student lane runs **after** workers return, in the parent (see `parallel_runner.run_scenarios_parallel`).

## Student-controlled replay produced separately

- **`attach_student_controlled_replay_v1`** runs a **second** `run_manifest_replay` with the same manifest window/candle settings, `emit_baseline_artifacts=False`, `decision_context_recall_enabled=False`, and validated `student_execution_intent_v1`.
- Results attach under **`student_controlled_replay_v1`** on each scenario row; baseline **`summary` / `replay_outcomes_json`** are not overwritten.

## Student intent digest tied to Student replay

- **`student_execution_intent_digest_v1`** and **`source_student_output_digest_v1`** are copied from the validated intent into **`student_controlled_replay_v1`**.

## Outcomes hash comparison

- **`control_outcomes_hash_v1`** — SHA-256 over canonical JSON of **`replay_outcomes_json`** (baseline worker).
- **`student_outcomes_hash_v1`** / **`outcomes_hash_v1`** — same over Student-lane **`outcomes`**.
- **`student_baseline_outcomes_differ_v1`** — boolean inequality of the two hashes when both exist.

## Trace: Referee used Student output (Student lane)

- On successful Student lane completion, **`referee_used_student_output`** is emitted with **`status: "true"`** and `evidence_payload` including `execution_lane_v1: student_controlled` ( **`learning_trace_instrumentation_v1` / `student_controlled_replay_v1`** producer).
- Additional stages: **`student_execution_intent_consumed`**, **`student_controlled_replay_started`**, **`student_controlled_replay_completed`** (see `learning_trace_events_v1`).

**Baseline** rows are unchanged by 024C (no `referee_used_student_output` true for control replay in this path).

## Example: Student lane can differ from baseline

- With **`enter_long` / `enter_short`**, the replay loop may open in the **intent direction** when fusion + risk would have opened a **baseline** entry — **direction** can differ from fusion (e.g. fusion long + intent `enter_short` → short entry).
- With **`no_trade`**, would-be entries from fusion are **suppressed** → often **fewer** entries and a different **outcomes hash** vs control.

## Scorecard

- **`record_parallel_batch_finished`** adds additive Student rollup fields (e.g. `student_controlled_replay_ran_v1`, `student_controlled_referee_win_pct_v1`, `student_controlled_expectancy_mean_v1`, `student_controlled_total_trades_sum_v1`) while preserving existing baseline `referee_win_pct` / `run_ok_pct` block.

## Tests

- `renaissance_v4/game_theory/tests/test_student_controlled_replay_v1.py` (mocked replay + invalid intent + error path + default kwarg + rollup).

## One-line summary

A **separate, scored** Student execution lane now consumes **`student_execution_intent_v1`** in a **parent-process** second replay, without merging Student outcomes into the baseline **control** row or **rewriting** the default `run_manifest_replay` control path.
