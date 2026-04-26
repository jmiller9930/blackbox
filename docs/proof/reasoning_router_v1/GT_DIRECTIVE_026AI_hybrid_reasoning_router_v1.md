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
PYTHONPATH=. python3 -m renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 smoke
```

**Expected:** JSON with `smoke_ok`, token fields, `model_resolved` when `OPENAI_API_KEY` is set; **no** `sk-` or `Authorization` in stdout. With no key, `smoke_ok` is false and no secret is printed.

**User already verified** `gpt-5.5-2026-04-23` in their environment; this command is the repeatable local proof pattern.

---

## 11. Deployment checklist (operator)

1. `git pull` on lab host; confirm `HEAD` matches pushed `main`.
2. **gsync** per team process.
3. Restart **Flask** (Pattern game `:8765`) so new code and trace stages load.
4. Run:  
   `PYTHONPATH=. python3 -m pytest renaissance_v4/game_theory/tests/test_gt_directive_026ai_unified_reasoning_router_v1.py -q`

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
| `renaissance_v4/game_theory/unified_agent_v1/config/reasoning_router_config_v1.example.json` | Safe defaults example |

**Integration (existing file, additive):** `entry_reasoning_engine_v1.run_entry_reasoning_pipeline_v1` — optional `unified_agent_router` and `router_*` kwargs.

---

## One-line

Build the unified-agent reasoning router so the Student uses local **qwen3-coder:30b** by default, escalates to **OpenAI** only when justified, records cost and review metadata, and **never** lets any model bypass the deterministic engine or validator.
