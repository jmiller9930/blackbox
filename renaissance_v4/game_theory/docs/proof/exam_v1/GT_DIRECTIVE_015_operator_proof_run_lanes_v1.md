# GT_DIRECTIVE_015 — operator proof: Student **brain profiles** on the scorecard

**Purpose:** Show how operators distinguish **baseline (no memory / no LLM)**, **memory + context (stub Student)**, and **memory + context + LLM component** on the **same exam fingerprint**, with **model choice** as nested metadata (`student_llm_v1.llm_model`) under the LLM profile — not as separate top-level “lanes.”

## Fixture (committed)

Canonical JSON array: `renaissance_v4/game_theory/tests/fixtures/gt_directive_015_scorecard_fixture_lines.json`

| Row | `job_id` | `student_brain_profile_v1` | `llm_model` | `skip_cold_baseline` | `skip_reason` (excerpt) |
|-----|-----------|----------------------------|-------------|------------------------|---------------------------|
| Baseline | `fixture_gt015_cold_baseline_001` | `baseline_no_memory_no_llm` | *null* | `false` | `mode_is_cold_baseline` |
| Memory+context | `fixture_gt015_repeat_anna_002` | `memory_context_student` | *null* | `true` | `prior_anchor_job_id=…001` |
| LLM + Qwen tag | `fixture_gt015_llm_qwen_003` | `memory_context_llm_student` | `qwen2.5:7b` | `true` | `prior_anchor_job_id=…001` |
| LLM + DeepSeek tag | `fixture_gt015_llm_deepseek_004` | `memory_context_llm_student` | `deepseek-r1:14b` | `true` | `prior_anchor_job_id=…001` |
| Skip-cold audit | `fixture_gt015_skip_cold_proof_005` | `memory_context_student` | — | `true` | `prior_anchor_job_id=…001` |

All rows share `memory_context_impact_audit_v1.run_config_fingerprint_sha256_40` = forty literal `a` characters.

## HTTP / API (live server)

- **POST** `/api/run-parallel/start` — body may include:

```json
{
  "exam_run_contract_v1": {
    "student_brain_profile_v1": "memory_context_llm_student",
    "student_llm_v1": {
      "llm_provider": "ollama",
      "llm_model": "deepseek-r1:14b",
      "llm_role": "single_shot_student_output_v1"
    },
    "skip_cold_baseline_if_anchor": true,
    "prompt_version": "student_llm_prompt_v0.1",
    "retrieved_context_ids": []
  }
}
```

- **Legacy** `student_reasoning_mode` lane strings (e.g. `llm_assisted_anna_qwen`) are still accepted and normalize to `memory_context_llm_student` with inferred `llm_model` when `student_llm_v1` is omitted.

- **GET** `/api/student-panel/runs` — rows reflect merged scorecard fields once batches complete.

## Honesty note (v1 engine)

**Physical** skip of Referee cold replay when an anchor exists is **not** implemented — parallel replay always runs. `skip_cold_baseline` / `skip_reason` are **metadata** for comparison validity.

For the LLM profile, **`student_llm_execution_v1`** records Ollama attempts; **`student_brain_profile_v1`** + **`llm_model`** must match the operator’s declared run contract (no silent global swap).
