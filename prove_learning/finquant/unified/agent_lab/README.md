# FinQuant Unified Agent Lab

**Status:** Scaffold (Phase 0 — lifecycle closure proof)  
**Architecture directive:** `docs/architect/FINQUANT_UNIFIED_AGENT_LAB_ARCHITECTURE_001.md`

---

## Isolation boundary

This lab is **self-contained**. It does not depend on:
- The web application being live
- Flask, any API server, or the dashboard
- The Student seam runtime
- Existing replay runners or operator batch code

No service restart is required to run the lab.

---

## What this lab proves

A FinQuant trade lifecycle:

```
observe candle context
→ interpret market state
→ decide NO_TRADE or ENTER
→ if entered, evaluate each new candle
→ decide HOLD or EXIT
→ close the lifecycle
→ grade outcome
→ write learning record
→ retrieve eligible prior records in a later run
```

---

## Configuration

| File | Purpose |
|------|---------|
| `configs/default_lab_config.json` | **Default:** Ollama LLM (`qwen2.5:7b`, host from `ollama_base_url_v1`). Falls back to deterministic logic only if the LLM call fails. |
| `configs/stub_lab_config.json` | **Offline / CI:** no LLM; fixed deterministic rules only. |
| `configs/llm_lab_config.json` | Same settings as `default_lab_config.json` (kept for explicit naming in docs/scripts). |

---

## Quick start

```bash
# Scaffold check (no cases required)
python finquant/unified/agent_lab/runner.py --scaffold-check

# Run the basic lifecycle case (default config = LLM; requires reachable Ollama)
python finquant/unified/agent_lab/runner.py \
  --case finquant/unified/agent_lab/cases/lifecycle_basic_v1.json \
  --config finquant/unified/agent_lab/configs/default_lab_config.json \
  --output-dir finquant/unified/agent_lab/outputs

# Same run without any LLM (airplane mode / CI)
python finquant/unified/agent_lab/runner.py \
  --case finquant/unified/agent_lab/cases/lifecycle_basic_v1.json \
  --config finquant/unified/agent_lab/configs/stub_lab_config.json \
  --output-dir finquant/unified/agent_lab/outputs

# Same runner with script-friendly runtime selectors
python finquant/unified/agent_lab/runner.py \
  --case finquant/unified/agent_lab/cases/lifecycle_basic_v1.json \
  --config finquant/unified/agent_lab/configs/default_lab_config.json \
  --data-window-months 12 \
  --interval 15

# Observable training cycle:
# seed memory -> control run -> memory/context run -> referee report
python finquant/unified/agent_lab/training_cycle.py \
  --seed-case finquant/unified/agent_lab/cases/trend_entry_exit_v1.json \
  --candidate-case finquant/unified/agent_lab/cases/memory_candidate_threshold_v1.json \
  --config finquant/unified/agent_lab/configs/default_lab_config.json \
  --output-dir finquant/unified/agent_lab/outputs \
  --data-window-months 12 \
  --interval 1hour

# Named test pack (default --config is stub for fast, deterministic packs)
python finquant/unified/agent_lab/test_framework.py \
  --test-pack finquant/unified/agent_lab/test_packs/learning_smoke_v1.json \
  --output-dir finquant/unified/agent_lab/outputs \
  --data-window-months 12 \
  --interval 1hour

# Run A / Run B with apples-to-apples replay (default --run-b-mode replay_run_a).
# Proof pack: marginal case flips NO_TRADE → ENTER_LONG once Run A wrote a PROMOTE long lesson.
python finquant/unified/agent_lab/run_ab_comparison.py \
  --cases-dir finquant/unified/agent_lab/cases/ab_memory_replay_pack \
  --config finquant/unified/agent_lab/configs/stub_lab_config.json \
  --output-dir finquant/unified/agent_lab/outputs \
  --run-a-fraction 1 \
  --run-b-mode replay_run_a

python finquant/unified/agent_lab/operator_report.py --latest --output-dir finquant/unified/agent_lab/outputs
```

---

## Structure

| File / Dir | Role |
|-----------|------|
| `runner.py` | Entry point — orchestrates case loading, lifecycle, evaluation, output |
| `case_loader.py` | Loads and validates case packs |
| `data_contracts.py` | Builds the causal input packet with math features, context, hypotheses, and memory summary |
| `lifecycle_engine.py` | Steps through candle context; hides future bars; emits decisions |
| `decision_contracts.py` | `finquant_decision_v1` schema enforcement |
| `execution_flow.py` | Shared execution path used by runner and training cycle |
| `evaluation.py` | Grades outcome; writes learning records |
| `learning_governance.py` | Governs whether a run can become retrievable memory |
| `memory_store.py` | Durable JSONL store for learning records |
| `retrieval.py` | Retrieves eligible prior records for a new run |
| `training_cycle.py` | Seed/train -> control -> memory/context -> referee artifact |
| `test_framework.py` | Runs named test packs and writes a top-level test summary |
| `schemas/` | JSON Schema definitions for all contracts |
| `cases/` | Case pack JSON files |
| `test_packs/` | Named isolated test packs |
| `configs/` | Agent lab configuration |
| `outputs/` | Per-run output artifacts (gitignored contents, `.gitkeep` only) |
| `docs/` | Architecture notes |

---

## First acceptance bar

A passing proof must show:
```
cases_loaded > 0
decisions_emitted > 0
learning_records_written == cases_processed
leakage_audit.pass == true
outputs_written == true
```

For the observable learning cycle, the expected end-state is:

```
seed_memory_written > 0
control_run_present == true
candidate_run_present == true
retrieval_match_count > 0
referee_report_exists == true
verdict_v1 in {"LEARNED_BEHAVIOR_PROVEN", "MEMORY_MATCH_NO_IMPACT", "BEHAVIOR_CHANGED_NOT_PROVEN_BETTER"}
```

For the test framework, the expected top-level artifacts are:

```
test_framework_summary.json exists
test_framework_summary.md exists
tests_total > 0
overall_status_v1 in {"PASS", "FAIL"}
```
