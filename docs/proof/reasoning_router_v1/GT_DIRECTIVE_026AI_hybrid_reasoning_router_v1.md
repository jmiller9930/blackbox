# GT_DIRECTIVE_026AI — Hybrid local / API reasoning router (proof)

## Summary

The **unified agent boundary** package `renaissance_v4/game_theory/unified_agent_v1/` implements a **reasoning router** that keeps **local Ollama** (`qwen3-coder:30b` at `http://172.20.1.66:11434`, overridable only via `STUDENT_OLLAMA_BASE_URL` / config `local_ollama_base_url`) as the **primary** path and allows an **optional** OpenAI **Responses** call (`gpt-5.5`, overridable via `OPENAI_REASONING_MODEL` / config) when **escalation reasons** and **budget** allow it.

**Authority:** `entry_reasoning_engine_v1` remains the **final** decision path; `validate_student_output_v1` remains the gate. External output is **`external_reasoning_review_v1`** (advisory only).

**Secrets:** API keys are read only from the environment name in config (`api_key_env_var`, default `OPENAI_API_KEY`). No key is stored in JSON, returned in router objects, or written to trace evidence (sanitized emits).

---

## 1. Local-only decision

With `external_api_enabled: false` (default in `reasoning_router_config_v1` / example JSON), `apply_unified_reasoning_router_v1` / `run_entry_reasoning_pipeline_v1(..., unified_agent_router=True)` yields `final_route_v1` in `{ local_only, external_blocked_config }` and no external review object.

**Automated:** `test_local_only_when_external_disabled` in `test_gt_directive_026ai_unified_reasoning_router_v1.py`.

---

## 2. External blocked — missing key

With `external_api_enabled: true` and the env var unset (or empty), `final_route_v1 == external_blocked_missing_key` and the fault-map operator line states the key was not configured.

**Automated:** `test_external_blocked_missing_key`.

---

## 3. External blocked — no escalation reason

With escalation reasons disabled or not detected (e.g. only `memory_conflict_v1` enabled and no conflict), `no_escalation_reason_v1` appears in blockers and no external call is made.

**Automated:** `test_external_blocked_no_escalation_reason`.

---

## 4. External called — low confidence (mocked OpenAI)

With `low_confidence_threshold` set high (e.g. `0.99`) so engine confidence is “low”, and `external_api_enabled: true` + key set, the router attempts a call. Tests **mock** `call_openai_responses_v1` on `reasoning_router_v1` so CI does not hit the network. A valid parsed JSON body becomes `external_reasoning_review_v1` with `validator_status_v1 == accepted` on the ledger.

**Automated:** `test_external_called_low_confidence_mocked`.

---

## 5. External — memory / conflict path (mocked)

`test_memory_conflict_triggers_mocked` exercises retrieval + router with a mocked Responses handler (connectivity-independent).

---

## 6. Invalid external output rejected

Malformed or wrong-schema `parsed_json` forces `final_route_v1 == external_failed_fallback_local` and no accepted `external_reasoning_review_v1`.

**Automated:** `test_invalid_external_rejected`.

---

## 7. Cost governor blocks a call

`max_external_calls_per_run: 0` (explicit; `0` is not coerced to `1`) prevents an external attempt even when reasons exist; `final_route_v1` is `external_blocked_budget` (or equivalent blocked state without a successful review).

**Automated:** `test_external_blocked_budget`.

---

## 8. Router trace events

Stages added to `EVENT_STAGES_V1` and emitted via `learning_trace_instrumentation_v1`:

- `reasoning_router_decision_v1`
- `external_reasoning_review_v1`
- `reasoning_cost_governor_v1`

Evidence payloads **strip** key-like fields defensively.

---

## 9. Fault map — router nodes

`NODE_IDS_ORDER` includes:

- `reasoning_router_evaluated`
- `external_escalation_governed`
- `external_reasoning_review_recorded`

**Automated:** `test_fault_map_has_router_nodes`; 026R debug test updated to `len(nodes) == len(NODE_IDS_ORDER)` (13 nodes after merge).

---

## 10. OpenAI smoke test (no key printed)

```bash
cd /path/to/blackbox
# Optional: override model (default for smoke: gpt-4o-mini if unset)
export OPENAI_REASONING_MODEL=gpt-4o-mini
PYTHONPATH=. python3 -m renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 smoke
```

**Expected:** JSON with `smoke_ok`, token fields, `model_resolved` when `OPENAI_API_KEY` is set; **no** `sk-` or `Authorization` in stdout. With no key, `smoke_ok` is false and no secret is printed.

`run_smoke_test_strict_json_v1` uses `OPENAI_REASONING_MODEL` when set; otherwise it defaults to **`gpt-4o-mini`** for broad API compatibility. Override for lab-specific models (e.g. `gpt-5.5`).

### 10a. Mandatory scenario artifacts (all failure/success paths)

**Location:** `docs/proof/reasoning_router_v1/scenario_artifacts_v1/`

| File | Scenario |
|------|-----------|
| `S01_local_only.json` | External disabled; local / blocked config |
| `S02_missing_api_key.json` | `OPENAI_API_KEY` unset; `missing_api_key_v1` |
| `S03_insufficient_funds.json` / `S03a_quota_exceeded.json` | Simulated 402/403 body → funding/quota; L1 **Add funds** URL |
| `S04_budget_exceeded.json` | Internal governor; no call |
| `S05_success_external_mocked.json` | Escalation + mock success; tokens/cost/latency on ledger |
| `S06_schema_failure.json` | Invalid body → `schema_validation_failed_v1` |
| `S07_disagreement_engine_unchanged.json` | External suggests different action; engine unchanged; `router_external_influence_v1` |
| `S08_rate_limited.json` / `S08b_provider_unavailable.json` | 429 / network style → `rate_limited_v1` / `provider_unavailable_v1` |
| `index_v1.json` | Manifest |
| `LIVE_SMOKE_openai_responses.json` | **Only** after `pytest -m integration` with a real key (see §10b) |

Each bundle is **`gt_directive_026ai_scenario_proof_bundle_v1`**: `router_decision_v1`, `external_api_call_ledger_v1`, `l1_fields_v1`, `fault_map_excerpt_v1` (`reasoning_router_evaluated`), `trace_events_representative_v1`, `operator_message_english_v1`, `required_fields_verification_v1`, `security_serialized_scan_v1` (must not contain `sk-` / `Bearer`).

**Regenerate (CI-safe, no network):**

```bash
PYTHONPATH=. python3 -m pytest renaissance_v4/game_theory/tests/test_gt_directive_026ai_mandatory_scenario_proofs_v1.py -m "not integration" -q
```

**Real gateway (must pass with valid key; requires network):**

```bash
export OPENAI_API_KEY=...   # your key, never commit
# Optional: match lab model (default smoke model is gpt-4o-mini if unset)
export OPENAI_REASONING_MODEL=gpt-5.5-2026-04-23
PYTHONPATH=. python3 -m pytest renaissance_v4/game_theory/tests/test_gt_directive_026ai_mandatory_scenario_proofs_v1.py -m integration -q
```

### 10b. Final closure artifact — `LIVE_SMOKE_openai_responses.json`

The integration test calls `build_live_026ai_closure_artifact_v1()` (in `gt_directive_026ai_proof_scenarios_v1.py`):

1. **`adapter_responses_api_smoke_v1`** — `run_smoke_test_strict_json_v1()` → `call_openai_responses_v1` / OpenAI `/v1/responses`. Must show `smoke_ok: true`, `provider: "openai"`, `model_requested`, `model_resolved`, `input_tokens`, `output_tokens`, `total_tokens`, `latency_ms`. No API key material.
2. **`reasoning_router_unified_path_v1`** — only if (1) succeeds: one `run_entry_reasoning_pipeline_v1(..., unified_agent_router=True)` with `external_api_enabled` and low-confidence escalation, proving the **same adapter** through the **unified reasoning router** (ledger + `final_route_v1` + L1 excerpt + fault-map node excerpt).
3. **`security_full_artifact_scan_v1`** — entire written JSON must not contain `sk-` or `Bearer ` when serialized.

`closure_complete_v1: true` means adapter smoke succeeded **and** the entry pipeline returned with no engine errors.

**Implementation:** `renaissance_v4/game_theory/unified_agent_v1/gt_directive_026ai_proof_scenarios_v1.py` — one function per scenario; tests assert mandatory fields and write JSON; `build_live_026ai_closure_artifact_v1` for live closure only.

---

## 11. Deployment checklist (operator)

1. `git pull` on lab host; confirm `HEAD` matches pushed `main`.
2. **gsync** per team process.
3. Restart **Flask** (Pattern game `:8765`) so new code and trace stages load.
4. Run:  
   `PYTHONPATH=. python3 -m pytest renaissance_v4/game_theory/tests/test_gt_directive_026ai_unified_reasoning_router_v1.py`  
   `renaissance_v4/game_theory/tests/test_gt_directive_026ai_mandatory_scenario_proofs_v1.py`  
   and optional `-m integration` for live OpenAI smoke.

---

## Files (new)

| Path | Role |
|------|------|
| `renaissance_v4/game_theory/unified_agent_v1/__init__.py` | Package exports |
| `renaissance_v4/game_theory/unified_agent_v1/reasoning_router_v1.py` | Router + advisory attach |
| `renaissance_v4/game_theory/unified_agent_v1/reasoning_router_config_v1.py` | Config load + env overrides |
| `renaissance_v4/game_theory/unified_agent_v1/reasoning_cost_governor_v1.py` | Token / call / dollar caps |
| `renaissance_v4/game_theory/unified_agent_v1/local_llm_adapter_v1.py` | Student Ollama (no model/host fallback) |
| `renaissance_v4/game_theory/unified_agent_v1/external_openai_adapter_v1.py` | OpenAI `/v1/responses` + smoke |
| `renaissance_v4/game_theory/unified_agent_v1/gt_directive_026ai_proof_scenarios_v1.py` | Mandatory scenario proof generators |
| `renaissance_v4/game_theory/tests/test_gt_directive_026ai_mandatory_scenario_proofs_v1.py` | Proof tests + JSON artifact writer |
| `docs/proof/reasoning_router_v1/scenario_artifacts_v1/*.json` | Committed proof bundles (regenerated by tests) |
| `renaissance_v4/game_theory/unified_agent_v1/config/reasoning_router_config_v1.example.json` | Safe defaults example |

**Integration (existing file, additive):** `entry_reasoning_engine_v1.run_entry_reasoning_pipeline_v1` — optional `unified_agent_router` and `router_*` kwargs.

---

## One-line

Build the unified-agent reasoning router so the Student uses local **qwen3-coder:30b** by default, escalates to **OpenAI** only when justified, records cost and review metadata, and **never** lets any model bypass the deterministic engine or validator.
