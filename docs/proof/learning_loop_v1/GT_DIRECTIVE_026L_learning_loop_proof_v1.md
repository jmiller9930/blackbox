# GT_DIRECTIVE_026L — Learning loop causal proof (`learning_loop_proof_graph_v1`)

This document records **what the operator sees** when validating Run A → Run B learning: a **node graph** with **stored evidence only** (no free-text-only proof). **Closure expectation:** operators use the **UI** as the primary path; the API remains for automation.

## Where to open (operator path)

1. **Student / Learning area (D11):** on a selected run, use **“A→B learning proof (026L)”** — it opens the debug page with **Run B** set to the current run. Enter **Run A** (the earlier run that created the lesson) and click **Load A→B proof**.  
2. **Learning loop trace** (`/learning-loop-trace?job_id=...`): use **“A→B learning proof (026L)”** in the nav for the same prefill.  
3. **Direct pages:** `/debug/learning-loop` or alias **`/debug/learning-loop-proof`** (same page; query string preserved). Optional query: `?run_a=...&run_b=...&job_id=...` (`job_id` still loads the legacy single-run trace at the bottom).

You do not need to remember API URLs, query names, the materialize command, or internal schema names to review a proof in the default view.

## What Run A and Run B mean

- **Run A** — The run that **created** the lesson: the graph checks that this run’s artifacts exist in the learning store (for example sealed student reasoning and memory promotion rules).  
- **Run B** — A **later** run that should **retrieve and use** that lesson in the packet, reasoning, and downstream decisions. The tool compares A vs B on the scorecard and store-backed evidence.

## What “learning confirmed” actually requires

`LEARNING_CONFIRMED` is only emitted when the **entire** defined chain passes (all relevant nodes, including memory effect, Run B retrieval, student packet and reasoning, decision and execution movement where required, and score-line comparison). If any required step fails or is not proven, the verdict is **not** “learning confirmed” — often `LEARNING_NOT_CONFIRMED` or a **`LOOP_BROKEN_AT_NODE_…`** code naming the first failing node.  

**Important:** a **short** `nodes_v1` list in a real response (for example 2 nodes) is **not** a defect — the builder **stops** when a step fails, so you will not see all 17 nodes until the underlying lab/store data satisfies the full chain.

## Interpreting verdicts (plain language)

| `final_verdict_v1` | Meaning |
|--------------------|--------|
| `LEARNING_CONFIRMED` | Full causal chain passed under the 026L rules. |
| `LEARNING_NOT_CONFIRMED` | Missing links, inconclusive evidence, or “not comparable” — see breakpoints and first failed node. |
| `INSUFFICIENT_DATA` | Not enough scorecard or store data to run the comparison. |
| `LOOP_BROKEN_AT_NODE_<id>` | Chain failed at the named node; everything listed before that step is in evidence; this node is the stop. |

## Common breakpoints (examples)

- Codes mentioning **`memory_had_no_effect`** — memory was classified in a way that cannot confirm learning.  
- Codes mentioning **`reasoning_missing`** (or similar) — Run A does not have the sealed reasoning the graph needs.  
- Codes about **retrieval** — Run B did not show retrieval of the Run A record in the trace/packet as required.

See `operator_summary_v1` and the on-page breakpoint hints in the debug UI for the exact lab-specific codes.

## API (automation / CI)

- `GET /api/training/learning-loop-proof?run_a=<job_id>&run_b=<job_id>`  
  Returns `learning_loop_proof_graph_v1`, `final_verdict_v1`, `breakpoints_v1`, `operator_summary_v1`.
- `POST /api/training/learning-loop-proof/materialize` with JSON body `run_a`, `run_b`, optional `baseline_job_id`, and `confirm: "MATERIALIZE_LEARNING_LOOP_PROOF_V1"`.

## Debug UI (same as “where to open”)

Use **Load A→B proof** on `/debug/learning-loop` to render the **final verdict** (with plain-English line), **operator summary**, **first failed node**, **node-by-node table**, and optional raw evidence — without reading the JSON. **Download proof JSON** saves the last response for an audit package.

## Real lab proof (not fixture-only)

A captured **lab** response (full `learning_loop_proof` API body) is kept at  
`docs/proof/learning_loop_v1/lab_example_2026-04-24_clawbot_1a37_vs_8922.json`  
(Run A = `1a37cc83d74c4ea1a974d56fc1caa360`, Run B = `8922b1a8bdb949d6ab864f73c8beeccb`). On that snapshot the graph **breaks early** (node 2 / reasoning) so **`nodes_v1` has two entries**, not 17 — that is consistent with the rules above. A run that yields all 17 nodes requires the lab store to satisfy every step.

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
