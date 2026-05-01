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

## Quick start

```bash
# Scaffold check (no cases required)
python finquant/unified/agent_lab/runner.py --scaffold-check

# Run the basic lifecycle case
python finquant/unified/agent_lab/runner.py \
  --case-pack finquant/unified/agent_lab/cases/lifecycle_basic_v1.json \
  --config finquant/unified/agent_lab/configs/agent_lab_config_v1.json \
  --output-dir finquant/unified/agent_lab/outputs
```

---

## Structure

| File / Dir | Role |
|-----------|------|
| `runner.py` | Entry point — orchestrates case loading, lifecycle, evaluation, output |
| `case_loader.py` | Loads and validates case packs |
| `lifecycle_engine.py` | Steps through candle context; hides future bars; emits decisions |
| `decision_contracts.py` | `finquant_decision_v1` schema enforcement |
| `evaluation.py` | Grades outcome; writes learning records |
| `memory_store.py` | Durable JSONL store for learning records |
| `retrieval.py` | Retrieves eligible prior records for a new run |
| `schemas/` | JSON Schema definitions for all contracts |
| `cases/` | Case pack JSON files |
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
