# GT_DIRECTIVE_026L — Learning loop causal proof (`learning_loop_proof_graph_v1`)

This document records **what the operator sees** when validating Run A → Run B learning: a **node graph** with **stored evidence only** (no free-text-only proof).

## API

- `GET /api/training/learning-loop-proof?run_a=<job_id>&run_b=<job_id>`  
  Returns `learning_loop_proof_graph_v1`, `final_verdict_v1`, `breakpoints_v1`, `operator_summary_v1`.
- `POST /api/training/learning-loop-proof/materialize` with JSON body `run_a`, `run_b`, optional `baseline_job_id`, and `confirm: "MATERIALIZE_LEARNING_LOOP_PROOF_V1"`.

## Debug UI

Open `/debug/learning-loop?run_a=<job_id>&run_b=<job_id>` (optionally with `job_id` for the legacy trace). Use **Load learning-loop proof** to render every proof node (status, evidence, explanation).

## Example verdicts (from automated fixtures)

| Case | `final_verdict_v1` | Notes |
|------|----------------------|--------|
| Full chain: promoted memory, strict retrieval, reasoning, non–`no_effect`, decision change, execution+score change | `LEARNING_CONFIRMED` | See `test_confirmed_learning_chain` |
| Run B did not link to Run A record in reasoning / trace | `LEARNING_NOT_CONFIRMED` or `LOOP_BROKEN_AT_NODE_node_10_…` | See `test_run_b_retrieval_not_proven` |
| Memory in packet but wrong `record_id` | `LEARNING_NOT_CONFIRMED` (node 11 fail) | See `test_memory_in_packet_fails` |
| Decision changed but batch outcomes hash and L1 E/P match Run A | `LEARNING_NOT_CONFIRMED` | See `test_decision_change_execution_unchanged_not_confirmed` |
| Declared `no_effect` / ignore-class memory | `LEARNING_NOT_CONFIRMED`, breakpoint `memory_had_no_effect_v1` | See `test_no_memory_effect_not_confirmed` |

## Operator-readable summary

The field `operator_summary_v1` is plain English: it states the final result, which runs were compared, and lists breakpoint codes plus the first failed node when present. It avoids abbreviations like “E/P”; node evidence still carries L1 scalar labels where applicable.

## Minimal graph JSON example (shape)

```json
{
  "schema": "learning_loop_proof_graph_v1",
  "contract_version": 1,
  "source_run_id_v1": "job_a",
  "target_run_id_v1": "job_b",
  "fingerprint_v1": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "candle_timeframe_minutes": 5,
  "nodes_v1": [
    {
      "node_id": "node_01_run_a_completed_v1",
      "node_type": "run_a_completed_v1",
      "status": "PASS",
      "producer": "learning_loop_proof_graph_v1",
      "evidence_fields_v1": ["status", "..."],
      "evidence_values_v1": { "job_id": "job_a", "status": "done" },
      "evidence_provenance_v1": ["batch_scorecard.jsonl"],
      "explanation_v1": "…",
      "required_for_learning_v1": true
    }
  ],
  "edges_v1": [
    { "edge_id": "edge_01_v1", "from_node_id": "node_01_run_a_completed_v1", "to_node_id": "node_02_run_a_student_reasoning_exists_v1" }
  ],
  "breakpoints_v1": [],
  "final_verdict_v1": "LEARNING_CONFIRMED",
  "operator_summary_v1": "Final result: LEARNING_CONFIRMED. …"
}
```

## Implementation reference

- Module: `renaissance_v4/game_theory/learning_loop_proof_graph_v1.py`
- Tests: `renaissance_v4/game_theory/tests/test_gt_directive_026l_learning_loop_proof_graph_v1.py`

## Store note (RSE in `student_output`)

Rows in `student_learning_store` must pass `validate_student_learning_record_v1`. Slices under `student_decision_packet_v1.retrieved_student_experience_v1` must not include forbidden outcome keys in nested objects (same pre-reveal rules as the rest of `student_output_v1`).
