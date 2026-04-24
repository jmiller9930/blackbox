# GT_DIRECTIVE_022 — Training export (operator proof)

## Scope

Read-only export of **`training_record_v1`** lines derived from **`student_learning_records_v1.jsonl`** joined to **`batch_scorecard.jsonl`** by `job_id` == `run_id`. **Promote-only**, **`status == done`**, full **§1.0 thesis** for **`memory_context_llm_student`**.

## Automated proof

- **Tests:** `renaissance_v4/game_theory/tests/test_gt_directive_022_training_export_v1.py`  
  - Promoted rows included; hold / running / incomplete thesis / missing governance excluded.  
  - NDJSON bytes **identical** across two exports with fixed `exported_at_utc`.  
  - HTTP **GET `/api/training/export`** returns `eligible_count == 2` on fixture store.

## Fixture counts (before → after)

| Metric | Value |
|--------|--------|
| Valid store rows | **6** |
| **Eligible training rows** | **2** |
| Filtered: not promote (hold) | **1** |
| Filtered: run not done | **1** |
| Filtered: thesis incomplete (LLM promote, missing thesis keys) | **1** |
| Filtered: missing governance | **1** |

Only **`record_id`** `11111111-…` (LLM + full thesis + promote + done) and **`55555555-…`** (baseline + promote + done) appear in export.

## Sample `training_record_v1` (trimmed)

```json
{
  "contract_version": 1,
  "created_utc": "2026-04-20T16:00:00Z",
  "directional_thesis_v1": {
    "confidence_band": "medium",
    "conflicting_indicators": ["atr_elevated"],
    "context_fit": "trend",
    "invalidation_text": "Close back below prior swing low.",
    "student_action_v1": "enter_long",
    "supporting_indicators": ["rsi_14", "ema_20_slope"]
  },
  "exported_at_utc": "FIXED_TS",
  "fingerprint_sha256_40": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "graded_unit_id": "trade_llm_1",
  "learning_governance_v1": { "decision": "promote", "schema": "learning_governance_v1" },
  "llm_model": "qwen-test:7b",
  "outcome_summary_v1": {
    "exam_e_score_v1": 0.8125,
    "exam_p_score_v1": 0.9,
    "exam_pass_v1": true,
    "expectancy_per_trade": 0.05
  },
  "promotion_decision": "promote",
  "run_id": "run_promote_llm",
  "schema": "training_record_v1",
  "source_learning_record_id": "11111111-1111-1111-1111-111111111111",
  "student_brain_profile_v1": "memory_context_llm_student",
  "student_output_v1": { "schema": "student_output_v1", "…": "…" },
  "student_proctor_contract_version": 1
}
```

Keys in real output are **sorted** (`sort_keys=True`) for deterministic bytes.

## HTTP verification (local)

```bash
curl -s "http://127.0.0.1:8765/api/training/export?preview=5" | python3 -m json.tool | head
curl -s "http://127.0.0.1:8765/api/training/export?download=1" -o /tmp/training_dataset_v1.jsonl
wc -l /tmp/training_dataset_v1.jsonl
```

Expect **`eligible_count`** consistent with store; download line count equals **`eligible_count`**.

## Materialize (server file)

```bash
curl -s -X POST "http://127.0.0.1:8765/api/training/export/materialize" \
  -H "Content-Type: application/json" \
  -d '{"confirm":"MATERIALIZE_TRAINING_DATASET_V1"}' | python3 -m json.tool
```

Writes **`PATTERN_GAME_TRAINING_DATASET_V1`** or default under runtime `student_learning/`.
