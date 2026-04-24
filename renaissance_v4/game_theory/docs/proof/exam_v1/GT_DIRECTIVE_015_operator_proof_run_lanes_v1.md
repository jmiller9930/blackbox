# GT_DIRECTIVE_015 — operator proof: identifiable run lanes

**Purpose:** Show how operators (or scripts) distinguish **cold baseline**, **repeat Anna (memory/context)**, **Qwen**, and **DeepSeek** sits on the **same exam fingerprint** using persisted scorecard fields.

## Fixture (committed)

Canonical JSON array: `renaissance_v4/game_theory/tests/fixtures/gt_directive_015_scorecard_fixture_lines.json`

Each object is one **scorecard line** shape with:

| Lane | `job_id` | `student_reasoning_mode` | `llm_model` | `skip_cold_baseline` | `skip_reason` (excerpt) |
|------|-----------|----------------------------|-------------|------------------------|---------------------------|
| Cold baseline | `fixture_gt015_cold_baseline_001` | `cold_baseline` | *null* | `false` | `mode_is_cold_baseline` |
| Repeat Anna | `fixture_gt015_repeat_anna_002` | `repeat_anna_memory_context` | *null* | `true` | `prior_anchor_job_id=…001` |
| LLM Qwen | `fixture_gt015_llm_qwen_003` | `llm_assisted_anna_qwen` | `qwen2.5:7b` | `true` | `prior_anchor_job_id=…001` |
| LLM DeepSeek | `fixture_gt015_llm_deepseek_004` | `llm_assisted_anna_deepseek_r1_14b` | `deepseek-r1:14b` | `true` | `prior_anchor_job_id=…001` |
| Skip-cold audit row | `fixture_gt015_skip_cold_proof_005` | `repeat_anna_memory_context` | — | `true` | `prior_anchor_job_id=…001` |

All rows share `memory_context_impact_audit_v1.run_config_fingerprint_sha256_40` = forty literal `a` characters (see the JSON fixture) so they are **comparable** apples-to-apples for config/strip identity in this proof artifact.

## HTTP / API (live server)

- **POST** `/api/run-parallel/start` — **200** with `ok: true` when the body validates; **400** when `student_reasoning_mode` is unknown or LLM mode is requested with an invalid Ollama base URL (see `parse_exam_run_contract_request_v1`).
- Optional body block:

```json
{
  "exam_run_contract_v1": {
    "student_reasoning_mode": "llm_assisted_anna_deepseek_r1_14b",
    "skip_cold_baseline_if_anchor": true,
    "prompt_version": "student_llm_prompt_v0.1",
    "retrieved_context_ids": []
  }
}
```

- **GET** `/api/student-panel/runs` — returns run rows built from `batch_scorecard.jsonl`; new fields appear on each line once the server has appended rows with GT_DIRECTIVE_015 metadata.

## Honesty note (v1 engine)

`student_llm_contract_note_v1` may be set to `llm_mode_declared_student_stub_until_ollama_wired` until the Student seam calls Ollama per run-scoped model — **declared** mode and **`llm_model`** must still match the operator selection (no silent global swap).
