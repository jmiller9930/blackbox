# Proof — Student directional thesis (LLM profile precondition for GT_DIRECTIVE_017)

**Purpose:** Show that `memory_context_llm_student` runs **reject** incomplete Ollama JSON (missing §1.0 thesis), **accept** complete thesis payloads, persist thesis keys on `student_learning_record_v1` → `student_output`, and surface them on L3 via `build_student_decision_record_v1`.

## Contract

- Required thesis keys (LLM path only): `student_action_v1`, `confidence_band`, `supporting_indicators`, `conflicting_indicators`, `context_fit`, `invalidation_text` (plus existing core `student_output_v1` keys).
- Enforcement: `emit_student_output_via_ollama_v1` + `validate_student_output_directional_thesis_required_for_llm_profile_v1` in `contracts_v1.py`.
- Seam: no stub fallback when Ollama returns `None` / errors — see `student_loop_seam_after_parallel_batch_v1` and audit key `llm_student_output_rejections_v1`.

## Fixtures (committed)

| File | Role |
|------|------|
| `renaissance_v4/game_theory/tests/fixtures/student_output_thesis_llm_valid_v1.json` | Valid full thesis (same directory as pytest) |
| `renaissance_v4/game_theory/tests/fixtures/student_output_thesis_llm_incomplete_v1.json` | Core-only (expected thesis rejection) |

## Operator-visible JSON

After a successful LLM-assisted seam append, each `student_learning_record_v1` line in the learning JSONL embeds the full `student_output` object. Example (abbreviated) — same shape as the **valid** fixture:

```json
{
  "schema": "student_learning_record_v1",
  "student_output": {
    "schema": "student_output_v1",
    "direction": "long",
    "confidence_01": 0.72,
    "confidence_band": "high",
    "student_action_v1": "enter_long",
    "supporting_indicators": ["rsi_14", "ema_20"],
    "conflicting_indicators": ["atr_14"],
    "context_fit": "trend",
    "invalidation_text": "Close below prior swing low on this timeframe.",
    "reasoning_text": "…"
  }
}
```

L3 API (`GET` … `/decisions` / D14 builder) exposes flat aliases: `student_confidence_band`, `student_action_v1`, `student_supporting_indicators`, `student_conflicting_indicators`, `student_context_fit`, `student_invalidation_text`, `student_reasoning_text` (see `student_panel_d14.py`).

## Tests

- `tests/test_student_output_thesis_extension_v1.py` — thesis required validator + learning roundtrip.
- `tests/test_student_ollama_thesis_enforcement_v1.py` — mocked Ollama accept / reject.

## HTTP (optional)

Where the batch result merges seam audit JSON, confirm `llm_student_output_rejections_v1` is present and increments when the model returns incomplete thesis JSON.
