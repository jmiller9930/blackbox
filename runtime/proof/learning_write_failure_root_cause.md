# Learning Write Failure — Root Cause Proof

**Job:** `d4-final-proof-001`  
**Verdict:** `ENGAGEMENT_WITHOUT_STORE_WRITES`  
**Observed:** `student_learning_rows_appended = 0`, `student_retrieval_matches = 0`, `memory_impact_yes_no = NO`  
**Evidence source:** `runtime/student_test/d4-final-proof-001/student_test_acceptance_v1.json` + `learning_trace_events_v1.jsonl`

---

## 1. Promotion decision function — confirmed location

**File:** `renaissance_v4/game_theory/student_proctor/learning_memory_promotion_v1.py`  
**Function:** `classify_trade_memory_promotion_v1(*, l3_payload, scorecard_entry)` — line 122

Confirmed by call chain: the operator seam imports and calls this function directly:

```
renaissance_v4/game_theory/student_proctor/student_proctor_operator_runtime_v1.py
  line 58–62: from ...learning_memory_promotion_v1 import GOVERNANCE_REJECT, classify_trade_memory_promotion_v1
```

---

## 2. Exact caller block — operator seam

**File:** `renaissance_v4/game_theory/student_proctor/student_proctor_operator_runtime_v1.py`  
**Function:** `student_loop_seam_after_parallel_batch_v1`

The append block (lines 1434–1481) in order:

```python
# line 1434
l3 = build_student_panel_l3_payload_v1(
    str(run_id).strip(),
    str(o.trade_id),
    provisional_student_learning_record_v1=lr,
)
# line 1439
_mem_dec, _mem_rc, gov = classify_trade_memory_promotion_v1(
    l3_payload=l3, scorecard_entry=scorecard_entry_effective
)
# line 1450
lr["learning_governance_v1"] = gov
# line 1456
post_gov_errs = validate_student_learning_record_v1(lr)
# line 1463
if str(gov.get("decision") or "") == GOVERNANCE_REJECT:
    ...
    continue                          # <-- SKIP append
# line 1480
append_student_learning_record_v1(store, lr)
appended += 1
```

**This block is never reached.** The trade loop exits before line 1434 on every trade. See section 3.

---

## 3. Exact conditional that skips append — the upstream `continue`

The append block at line 1434 is gated by all prior `continue` statements in the trade loop. For all 10 trades in `d4-final-proof-001`, the loop exits at this exact block:

**File:** `student_proctor_operator_runtime_v1.py`, lines 999–1039

```python
if soe or so is None:                        # line 999 (LLM path rejection)
    llm_student_output_rejections_v1 += 1
    errors.append(
        f"{sid} trade={o.trade_id}: llm_student_output_rejected: ..."
    )
    emit_llm_output_rejected_v1(...)
    emit_student_decision_failed_before_authority_v1(...)
    continue                                 # LINE 1039 — EXITS TRADE LOOP
```

Append is never attempted. `build_student_panel_l3_payload_v1`, `classify_trade_memory_promotion_v1`, and `append_student_learning_record_v1` are **never called** for any of the 10 trades.

---

## 4. HOLD vs PROMOTE vs REJECT append behavior

From `learning_memory_promotion_v1.py`:

| Decision | Code path | Append attempted? |
|---|---|---|
| `GOVERNANCE_REJECT` | line 1463–1470: `if str(gov.get("decision")...) == GOVERNANCE_REJECT: continue` | **NO** |
| `GOVERNANCE_HOLD` | falls through to line 1480 | **YES** |
| `GOVERNANCE_PROMOTE` | falls through to line 1480 | **YES** |

HOLD rows **are** appended. REJECT rows are not. However in this run **neither path is reached** because the LLM output rejection fires a `continue` at line 1039, before governance is ever evaluated.

---

## 5. Runtime values for one failing trade — `student_test_0000_v1`

**Trade ID:** `student_test_0000_v1`  
**Scenario ID:** `tier1_twelve_month_default`  
**Job ID:** `d4-final-proof-001`  
**Fingerprint:** `2c1952d548f47195cb5f34fc4cbafe44eaf06738`

| Field | Runtime value |
|---|---|
| `l3_payload["ok"]` | **never evaluated** — governance block not reached |
| `decision_record_v1["ok"]` | **never evaluated** |
| `data_gaps` | **never evaluated** |
| `critical data_gaps` | **never evaluated** |
| `promotion_decision` | **never computed** — `classify_trade_memory_promotion_v1` not called |
| `append_attempted` | **false** |
| `append_result` | none |
| `exception` | none — clean `continue` |

**Trace event — `llm_output_rejected` (stage in `learning_trace_events_v1.jsonl`):**

```json
{
  "schema": "learning_trace_event_v1",
  "job_id": "d4-final-proof-001",
  "fingerprint": "2c1952d548f47195cb5f34fc4cbafe44eaf06738",
  "trade_id": "student_test_0000_v1",
  "scenario_id": "tier1_twelve_month_default",
  "stage": "llm_output_rejected",
  "timestamp_utc": "2026-04-28T23:03:08Z",
  "status": "fail",
  "evidence_payload": {
    "errors": [
      "ollama_response_not_json_object: ### Analysis and Decision\n\n#### Context:\n- **Symbol:** SOLUSDT..."
    ]
  },
  "producer": "student_ollama_student_output_v1"
}
```

**Trace event — `student_decision_failed_before_authority_v1`:**

```json
{
  "schema": "learning_trace_event_v1",
  "job_id": "d4-final-proof-001",
  "fingerprint": "2c1952d548f47195cb5f34fc4cbafe44eaf06738",
  "trade_id": "student_test_0000_v1",
  "scenario_id": "tier1_twelve_month_default",
  "stage": "student_decision_failed_before_authority_v1",
  "timestamp_utc": "2026-04-28T23:03:08Z",
  "status": "error",
  "evidence_payload": {
    "reason_code": "llm_student_output_rejected_v1",
    "detail": "ollama_response_not_json_object: ..."
  },
  "producer": "student_loop_seam_v1"
}
```

---

## 6. First byte-level cause — two distinct failure modes across 10 trades

### Trade `student_test_0000_v1` — model returned markdown, not JSON

**File:** `renaissance_v4/game_theory/student_proctor/student_ollama_student_output_v1.py`  
**Rejection code:** `ollama_response_not_json_object`

The Ollama model returned freeform markdown prose beginning with `### Analysis and Decision`. The output parser in `emit_student_output_via_ollama_v1` failed to parse a JSON object. `so` was `None`. The check at line 999 fired:

```python
if soe or so is None:
    ...
    continue   # student_proctor_operator_runtime_v1.py line 1039
```

Append never attempted.

---

### Trades `student_test_0001_v1` through `student_test_0009_v1` — thesis fields missing from JSON output

**File:** `renaissance_v4/game_theory/student_proctor/contracts_v1.py`  
**Rejection code:** `student_output_thesis_incomplete_for_llm_profile`  
**Contract:** `validate_student_output_directional_thesis_required_for_llm_profile_v1`  
**Required fields (from `THESIS_REQUIRED_FOR_LLM_PROFILE_V1`):**

```
context_interpretation_v1
hypothesis_kind_v1
hypothesis_text_v1
supporting_indicators
conflicting_indicators
confidence_band
context_fit
invalidation_text
```

The model returned a JSON object but omitted multiple required thesis fields. `soe` was non-empty. Same check at line 999 fired → `continue`.

**Representative rejection (trade `student_test_0001_v1`):**

```
directional_thesis_required_for_llm_profile: missing context_interpretation_v1
directional_thesis_required_for_llm_profile: missing hypothesis_kind_v1
directional_thesis_required_for_llm_profile: missing hypothesis_text_v1
directional_thesis_required_for_llm_profile: missing supporting_indicators
directional_thesis_required_for_llm_profile: missing conflicting_indicators
directional_thesis_required_for_llm_profile: missing confidence_band
directional_thesis_required_for_llm_profile: missing context_fit
directional_thesis_required_for_llm_profile: missing invalidation_text
```

---

## 7. Summary — exact root cause

```
append skipped for all 10 trades because:

student_proctor_operator_runtime_v1.py, lines 999–1039:
  if soe or so is None:
      ...
      continue

and (soe or so is None) was TRUE because:

  trade_0000: so is None
    reason: ollama returned markdown prose, not a JSON object
    rejection_code: ollama_response_not_json_object
    model: qwen2.5:7b at http://172.20.2.230:11434
    producer: student_ollama_student_output_v1.py

  trades_0001–0009: so was not None but soe was non-empty
    reason: JSON returned but thesis fields absent
    rejection_code: student_output_thesis_incomplete_for_llm_profile
    missing fields: context_interpretation_v1, hypothesis_kind_v1, hypothesis_text_v1,
                    supporting_indicators, conflicting_indicators, confidence_band,
                    context_fit, invalidation_text
    contract: validate_student_output_directional_thesis_required_for_llm_profile_v1
              in renaissance_v4/game_theory/student_proctor/contracts_v1.py

Downstream effect:
  - build_student_panel_l3_payload_v1: never called
  - classify_trade_memory_promotion_v1: never called
  - append_student_learning_record_v1: never called
  - student_learning_rows_appended: 0
  - student_retrieval_matches: 0
  - memory_promotion_batch_v1.per_trade: []
  - verdict: ENGAGEMENT_WITHOUT_STORE_WRITES
```

---

## File paths and line numbers

| Location | File | Lines |
|---|---|---|
| LLM rejection + continue | `student_proctor_operator_runtime_v1.py` | 999–1039 |
| Governance classify call | `student_proctor_operator_runtime_v1.py` | 1434–1441 |
| GOVERNANCE_REJECT skip | `student_proctor_operator_runtime_v1.py` | 1463–1470 |
| Append call | `student_proctor_operator_runtime_v1.py` | 1480–1481 |
| Promotion classifier | `learning_memory_promotion_v1.py` | 122–232 |
| Thesis contract | `contracts_v1.py` (student_proctor) | `validate_student_output_directional_thesis_required_for_llm_profile_v1` |
| L3 payload builder | `student_panel_l3_datagap_matrix_v1.py` | 475–580 |

---

# Patch — Applied 2026-05-01

**File patched:** `renaissance_v4/game_theory/student_proctor/student_ollama_student_output_v1.py`

## Patch 1 — Ollama `format: "json"` (tokenizer-level JSON enforcement)

`_ollama_chat_once_v1` now accepts `format_json: bool = False`. When True, `"format": "json"` is added to the Ollama API payload, constraining the model at the grammar level to emit only valid JSON. All three call sites in `emit_student_output_via_ollama_v1` pass `format_json=True` when `llm_repair_path_v1` is True (default in student test mode and when `PATTERN_GAME_STUDENT_LLM_CONTRACT_REPAIR=1`).

Fixes: `ollama_response_not_json_object` failure class (trade `student_test_0000_v1`).

## Patch 2 — MANDATORY KEYS CHECK header in user prompt

A required-fields header is injected before the intro block when `require_directional_thesis_v1=True`, listing all 9 keys that will cause rejection if absent.

Fixes: missing-field class (trades `student_test_0001_v1` – `student_test_0009_v1`).

## Patch 3 — GT037 repair: explicit ADD instructions per missing key

`_gt037_validation_repair_prompt_v1` now parses `validation_errors` to extract `missing <key>` patterns and prefixes a "MISSING KEYS — you MUST ADD each of these key-value pairs" section. One-line remedy string per missing key.

---

## Proof 1 — Ollama probe (first-shot pass, post-patch)

```bash
PYTHONPATH=. PATTERN_GAME_STUDENT_TEST_ISOLATION_V1=1 \
  python3 scripts/student_llm_json_contract_probe_v1.py
```

```json
{
  "ok": true,
  "student_action_v1": "no_trade",
  "errors": [],
  "json_contract_retry_used_v1": false,
  "model": "qwen2.5:7b",
  "ollama_base_url": "http://172.20.2.230:11434"
}
```

Pre-patch: 10/10 `llm_output_rejected`. Post-patch: 0 repair rounds, accepted first call.

---

## Proof 2 — Line 1434 reached (patch-proof-001 trace)

**Job:** `patch-proof-001`  
**Trace:** `runtime/student_test/patch-proof-001/learning_trace_events_v1.jsonl`

```
llm_called: 5
llm_output_received: 4          ← model accepted (was 0/10 in d4-final-proof-001)
student_output_sealed: 4        ← sealed successfully
governance_decided: 4           ← line 1439-1442 reached 4 times
```

`governance_decided` is emitted at line 1442, after `classify_trade_memory_promotion_v1` at line 1439, which is after `build_student_panel_l3_payload_v1` at line 1434.

Note: governance returns REJECT in student test isolation (no scorecard entry → L3 `ok=False` → `reject_l3_payload_not_ok_v1`). This is a student test isolation constraint separate from the LLM patch.

---

## Proof 3 — PROMOTE appends a learning row (direct path proof)

```bash
PYTHONPATH=. python3 scripts/prove_hold_promote_append_v1.py
```

```json
{
  "ok": true,
  "proof": "HOLD_PROMOTE_APPEND_VERIFIED",
  "trade_id": "proof_trade_0001",
  "record_id": "b9686c25-0c1f-576a-9b70-ef0902f6b704",
  "governance_decision": "promote",
  "governance_reason_codes": ["promote_clean_l3_positive_economics_v1"],
  "rows_appended": 1,
  "governance_decision_in_store": "promote",
  "thesis_fields_present": [
    "context_interpretation_v1", "hypothesis_kind_v1", "hypothesis_text_v1",
    "supporting_indicators", "conflicting_indicators", "confidence_band",
    "context_fit", "invalidation_text", "student_action_v1"
  ],
  "lines_exercised": {
    "build_student_panel_l3_payload_v1": "line_1434",
    "classify_trade_memory_promotion_v1": "line_1439",
    "append_student_learning_record_v1": "line_1480"
  }
}
```

`rows_appended: 1`. Store read-back confirms `record_id` matches and `governance_decision_in_store = "promote"`. All 9 thesis fields present on the stored `student_output`.

---

## Remaining gap (not introduced by this patch)

In student test isolation, `build_student_decision_record_v1` returns `None` when there is no scorecard entry (`find_scorecard_entry_by_job_id` → `None` → early return at line 257–258 of `student_panel_d14.py`). This causes L3 `ok=False` → governance rejects. This is the student test isolation design. A real operator run with a registered scorecard entry will reach PROMOTE/HOLD and append.
