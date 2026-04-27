# GT_DIRECTIVE_027 — RM preflight: operator contract (bounded replay + live status)

**Status:** **Normative v1** (engineering + operator).  
**Date:** 2026-04-27  
**To:** Engineering / Operator  
**Scope:** `rm_preflight_wiring_v1.py`, `parallel_runner._worker_run_one`, `web_app.py` job status / UI.

---

## Purpose

RM preflight proves **before** `run_scenarios_parallel` that the Student RM wiring path can emit the required trace stages with the **batch `job_id`**, and (when applicable) the Student decision protocol on sealed output. It must be **bounded** (not an unbounded “wait for a trade forever” full exam).

---

## What actually runs

1. **Scenario shrink** — `_shrink_scenario_for_rm_preflight_v1` on the first submitted scenario:
   - `evaluation_window.calendar_months` capped by `PATTERN_GAME_RM_PREFLIGHT_MAX_CALENDAR_MONTHS` (default **1**).
   - `rm_preflight_replay_tail_bars_v1` from `PATTERN_GAME_RM_PREFLIGHT_REPLAY_TAIL_BARS` (default **80**, min **50**).

2. **One worker row** — same entrypoint as the parallel batch: `_worker_run_one(shrunk)`. For normal recipes this calls `run_pattern_game(..., replay_max_bars_v1=tail)` so replay uses **only the last N bars** of the resolved tape (not the operator’s full window as unbounded bar work).

3. **Student seam** — `student_loop_seam_after_parallel_batch_v1(results=[row], run_id=job_id, ...)` with **memory trace sink** and **early exit** after the first `student_output_sealed` when the preflight context is active.

4. **Sink validation** — `validate_rm_preflight_memory_sink_detailed_v1` for required stages + job_id binding + sealed protocol flags (LLM profile).

**Exception:** Operator **learning harness** recipes in `_worker_run_one` use a different branch (`run_operator_test_harness_v1`, etc.) and do **not** apply `rm_preflight_replay_tail_bars_v1` the same way — those runs can be heavier; call out in operator docs if a recipe uses that path.

---

## Caps (defaults)

| Control | Env var | Default |
|--------|---------|---------|
| Calendar months (preflight) | `PATTERN_GAME_RM_PREFLIGHT_MAX_CALENDAR_MONTHS` | 1 |
| Replay tail bars | `PATTERN_GAME_RM_PREFLIGHT_REPLAY_TAIL_BARS` | 80 |
| Worker wall-clock wait | `PATTERN_GAME_RM_PREFLIGHT_WORKER_TIMEOUT_S` | 10s (clamped 3–120) |
| Heartbeat interval | `PATTERN_GAME_RM_PREFLIGHT_HEARTBEAT_INTERVAL_S` | 1.25s |

On worker timeout, audit includes **`preflight_timeout_waiting_for_trade_v1`**. If the worker returns **zero** closed trades in `replay_outcomes_json`, preflight fails **`no_replay_outcomes_for_preflight_v1`** (not an infinite wait).

---

## Operator-visible API (polling)

While `status` is `preflight`, `GET /api/run-status/<job_id>` (and `/api/run-parallel/status/...`) should surface:

- **`rm_preflight_results_panel_v1`** — checklist lines + bound `scenario_id` / `trade_id` when known.
- **`rm_preflight_telemetry_v1`** — `phase_v1`, `elapsed_s_v1`, `heartbeat_seq_v1`, `bars_replay_cap_v1`, optional `bars_processed_v1`, `replay_position_v1`, `note_v1`.
- **`preflight_display_status_v1`** — `preflight_active` during live preflight; `batch_running` after PASS when parallel starts; `preflight_failed` / `preflight_cancelled` / `preflight_cancelled_after_pass` on terminal paths.
- **`last_message`** — short human line including phase/elapsed when the progress callback runs.

---

## PASS / FAIL (summary)

- **PASS:** Worker OK → scenario/trade binding → seam reaches `rm_preflight_wiring_early_exit_v1` → sink validation `ok_v1`.
- **FAIL:** Worker error, **timeout**, scenario mismatch, empty outcomes, seam skip/errors, or sink missing required stages / protocol.

---

## Code map

| Piece | Module |
|--------|--------|
| Preflight orchestration | `rm_preflight_wiring_v1.run_rm_preflight_wiring_v1` |
| Worker | `parallel_runner._worker_run_one` |
| Replay tail | `pattern_game.run_pattern_game` → `replay_max_bars_v1` |
| Job + telemetry | `web_app._parallel_job_rm_preflight_progress_cb_v1`, `_parallel_job_enqueue_record_v1`, status handler |
