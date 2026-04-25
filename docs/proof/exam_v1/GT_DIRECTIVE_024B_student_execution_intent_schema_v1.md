# GT_DIRECTIVE_024B — Student execution intent schema (proof)

**Status:** CLOSED (schema + validation + tests + fixtures; **no replay wiring**).  
**Code:** `renaissance_v4/game_theory/student_proctor/student_execution_intent_v1.py`  
**Tests:** `renaissance_v4/game_theory/tests/test_student_execution_intent_v1.py`

## What was built

- **`student_execution_intent_v1`** — JSON-serializable object with required fields:
  `schema`, `schema_version`, `job_id`, `fingerprint`, `scenario_id` and/or `trade_id`,
  `student_brain_profile_v1`, `llm_model` (nullable), `source_student_output_digest_v1`,
  `student_execution_intent_digest_v1`, `action`, `direction`, `confidence_01`, `confidence_band`,
  `supporting_indicators`, `conflicting_indicators`, `context_fit`, `invalidation_text`, `created_at_utc`.
- **`build_student_execution_intent_from_sealed_output_v1`** — builder from sealed `student_output_v1` (schema `student_output_v1`) plus run identity.
- **§1.0 thesis (LLM):** For `memory_context_llm_student`, the builder delegates to
  `validate_student_output_directional_thesis_required_for_llm_profile_v1` (same rules as
  `contracts_v1` / Student–Proctor §1.0).
- **Digests:** `digest_sealed_student_output_v1` (canonical JSON, sorted keys) and
  `compute_student_execution_intent_digest_v1` (excludes `created_at_utc` and the intent digest field).
- **Trace readiness:** `student_execution_intent_trace_created_fields_v1` — data shape for a future
  `student_execution_intent_created` event (no runtime emit in 024B).

## Replay and scoring (unchanged)

- **`run_manifest_replay`** — not modified.
- **`parallel_runner._worker_run_one`** — not modified.
- **Scorecard / L1 / L2 / L3** — not modified.

## Valid intent example

Fixture: `renaissance_v4/game_theory/tests/fixtures/valid_student_execution_intent_enter_long_v1.json`

Built from sealed `tests/fixtures/student_output_thesis_llm_valid_v1.json` with fixed
`created_at_utc` for a reproducible file. `validate_student_execution_intent_v1` returns `[]` on
this file.

## Invalid rejection example

Fixture: `renaissance_v4/game_theory/tests/fixtures/invalid_student_execution_intent_action_direction_v1.json`

- `action` = `enter_long`, `direction` = `short` → `validate_student_execution_intent_v1` reports
  `action/direction mismatch (enter_long→long, enter_short→short, no_trade→flat)`.

## Digest stability (evidence)

- Unit tests `test_intent_digest_stable_excludes_timestamp` and
  `test_intent_deterministic_digest_same_inputs` show:
  - identical sealed Student output + same job id / fingerprint / scenario → same
    `student_execution_intent_digest_v1` even when `created_at_utc` differs;
  - same inputs, same `created_at_utc` → same digest.
- `source_student_output_digest_v1` is stable for identical `student_output_v1` dict semantics
  (canonical JSON over the full sealed object).

## One-line summary

The safe, validated execution-intent bridge from sealed Student reasoning to the future
Student-controlled replay lane is defined and test-proven **without** touching replay or batch
scoring.
