# Note to Training Engineer — From Cody

**Date:** 2026-05-04  
**Keep workstreams separate. Do not cross threads.**

---

## What you need to know right now

**While a long full QLoRA run is active (~24h): avoid corpus churn** — let the job finish; run **`finquant_llm_eval.py`** after; then execute the backlog below.

**Merged export already carries real ENTER rows** (`--good-only` ledger export → merge). The old “add two ENTER rows to seed-only” ask is **superseded for merged-corpus trains** — seed stays small; volume lives in export + merge.

**Integrated priorities (LE + Cody):** See **`training/CURRENT_TRAINING_STATUS.md` §5 — Corpus growth backlog** — memory density, contrast/conflict rows, authority-inventory stress cases, taxonomy alignment. That is the **next** training-stream focus after the current run.

**Workstream boundary unchanged:**

- `prove_learning/` — learning loop, ledger, exporter source (operator handoff).
- `training/` — corpus, validator, launcher, `train_qlora`, verifier.

---

## After the current train completes

1. Reports + adapter under **`FINQUANT_BASE`**; **`finquant_llm_eval.py`** per LE.
2. **`prepare` → `validate`** when changing corpus again.
3. Implement §5 backlog in **small batches** (memory-filled exports → curated stress JSONL → re-merge → validate).

---

## What I will provide when the operator says to merge

Validated JSONL from **`export_to_training_corpus.py`** plus merge policy — entries, stand-downs, INSUFFICIENT_DATA, schema per **`validate_agentic_corpus_v1.py`**.

— Cody
