# GT_DIRECTIVE_025 — Learning flow step validator (system-level proof, v1)

**Purpose:** Provide a **deterministic chain-of-proof** for whether **Run B** plausibly reflects **Run A**’s system-level learning handoffs. This **does not** claim model-weight training, hidden Student models, or that LLM sampling variance equals learning.

> **Explicit note:** *This validates system-level learning (control and data handoffs, scores, governance, and store/trace surfaces), not model training.*

## API

| Method | Path | Query / body |
|--------|------|----------------|
| `GET` | `/api/training/learning-flow-validate` | `run_a`, `run_b` = `job_id` (scorecard) |
| `POST` | `/api/training/learning-flow-validate/materialize` | JSON: `run_a`, `run_b`, `confirm` = `MATERIALIZE_LEARNING_FLOW_VALIDATION_V1` — writes a JSON audit on disk (default: `<runtime>/student_learning/learning_flow_validation_v1.json`) |

## Verdicts

| `verdict_v1` | When |
|--------------|------|
| `LEARNING_CONFIRMED` | All required Run A + Run B **steps** are `PASS` (or a governed `SKIPPED` where the directive allows), and Run B is explicitly linked to Run A in trace, with decision / execution / E deltas proven. |
| `LEARNING_NOT_CONFIRMED` | The pipeline is mostly observable, but a **necessary learning claim** is falsified (e.g. `11`..`13` `FAIL` on no-change) or `10` does not show evidence that Run B’s retrieval referenced Run A, or a weak-case branch applies. |
| `LOOP_BROKEN_AT_STEP_<n>` | A **structural** failure in Run A (steps 1–9) — e.g. memory read on but no retrieval, promote without store append, etc. |
| `INSUFFICIENT_DATA` | `NOT_PROVEN` on a critical step (1–8 or 11–12–13) when fields are missing, or **memory read mode** is off (step 1 `SKIPPED` — not applicable to the memory path). |

## Each step: status + evidence

Every step in `steps_v1` has:

- `status_v1` — one of `PASS` \| `FAIL` \| `SKIPPED` \| `NOT_PROVEN`
- `evidence_fields_v1` — exact data paths consulted
- `evidence_values_v1` — raw values (or a trace-only marker)
- `explanation_v1` — one short, deterministic line

**Rule:** the engine **does not** infer unlogged stages. Missing trace or scorecard fields → `NOT_PROVEN` (then typically `INSUFFICIENT_DATA` at verdict level, unless a later `FAIL` is more specific).

## Run A (steps 1–9) — what is checked

1. `memory_retrieved_v1` — `student_retrieval_matches` / MCI / trace `memory_retrieval_completed` (or memory lane `SKIPPED` if config is not read).
2. `memory_used_v1` — use or explicit **reject** path in trace (e.g. `llm_output_rejected`) or aligned retrieval/impact.
3. `student_decision_created_v1` — `student_output_fingerprint` and/or `student_output_sealed` in trace.
4. `student_execution_intent_created_v1` — `student_execution_intent_consumed` in trace and/or `student_execution_intent_digest_v1` on a batch row.
5. `student_execution_applied_v1` — 024C/024D path: trace `student_controlled_replay_*` and/or `student_controlled_replay_ran_v1` and/or a `student_controlled_replay_v1` block.
6. `execution_outcomes_generated_v1` — `outcomes_hash_v1` / `student_outcomes_hash_v1` and/or a completed student-controlled trace.
7. `score_computed_v1` — exam E/P on scorecard and/or `grading_completed` in trace.
8. `governance_decision_v1` — `governance_decided` in trace and/or `build_student_panel_run_learning_payload_v1` aggregate.
9. `learning_record_appended_v1` — **if promote:** trace `learning_record_appended` / `student_learning_rows_appended` / store rows; **if not promote** → `SKIPPED` (not required by governance).

## Run B (steps 10–13)

10. `memory_retrieved_from_run_A_v1` — **PASS** only when **trace** `evidence_payload` explicitly names Run A (e.g. `source_run_id` / `source_run_id_v1` / `source_record_id` tied to a Run A `record_id`). Otherwise: same fingerprint + retrieval count + store eligibility is documented as `NOT_PROVEN` (we **do not** claim which rows were in the packet without a trace line).
11. `student_decision_changed_v1` — compare `student_output_fingerprint` A vs B.
12. `execution_changed_v1` — compare `student_execution_intent_digest_v1` on the first `student_controlled_replay` row in each batch.
13. `score_changed_v1` — compare L1 E proxy (`line_e_value_for_l1_v1`).

## Working example (A → B)

- Run A: promote path completes; a learning row for `run_id=job_a` exists in the store; `learning_trace_events_v1` includes governance + append for A.
- Run B: `batch_parallel_results_v1` differs in digest, outcomes hash, and E; a trace line for B’s retrieval carries `source_run_id: "job_a"` in `evidence_payload`.
- **Result:** `verdict_v1` = `LEARNING_CONFIRMED` when steps 1–8 and 11–12–13 are `PASS`, step 9 is `PASS` (promote + append) or the governed `SKIPPED` cases match the directive, and step 10 is `PASS`.

## Broken loop example

- Run A: step 1 `FAIL` (memory read on, but zero `student_retrieval_matches` and no MCI/recall) → `LOOP_BROKEN_AT_STEP_1`.
- Or: steps 1–9 look fine, but Run B reuses the same execution digest and the same E — steps `11`–`13` `FAIL` → `LEARNING_NOT_CONFIRMED` (the system did not show a *change* between runs, even if the LLM looked different in chat).

## Trace integration (optional)

When present, use:

- `learning_trace_events_v1` (stages: `memory_retrieval_completed`, `student_output_sealed`, `student_execution_intent_consumed`, `student_controlled_replay_*`, `grading_completed`, `governance_decided`, `learning_record_appended`, …)
- `evidence_payload.student_execution_intent_digest_v1` and `student_outcomes_hash_v1` (where emitted)
- `outcomes_hash_v1` on the batch row’s `student_controlled_replay_v1`

**No blocking:** if a trace is empty, the validator falls back to **scorecard + `batch_parallel_results_v1` + store**; missing data becomes `NOT_PROVEN`, not a silent pass.

## Code map

| File | Role |
|------|------|
| `renaissance_v4/game_theory/learning_flow_validator_v1.py` | 13-step engine + `build_learning_flow_validation_v1`, `materialize_learning_flow_validation_v1` |
| `web_app.py` | `GET` / `POST` routes under `/api/training/learning-flow-validate` |
