# Note to Training Engineer — From Cody

**Date:** 2026-05-03  
**Keep workstreams separate. Do not cross threads.**

---

## What you need to know right now

**These two efforts stay isolated until the operator merges them:**

- `prove_learning/` — my scope (Cody). Learning loop, signal validation, ledger generation.
- `training/` — your scope. Corpus, QLoRA, model evaluation.

**Do not pull anything from `prove_learning/` into `training/` on your own. The operator bridges that handoff.**

---

## What I ask you to do — minimum necessary

**One thing only while the model trains:**

Add at least one `ENTER_LONG` and one `ENTER_SHORT` gold example to `training/corpus_v05_agentic_seed.jsonl` using the correct `finquant_agentic_qa_v1` schema.

The baseline showed 100% NO_TRADE because the model has never seen an entry example. That is the only corpus gap that directly blocks the next run from being better.

Use the schema already in the seed file (see rows 1-3 for structure). The key fields:
- `hypotheses_v1` (array, ≥2 entries)
- `Final_status: "ENTER_LONG"` or `"ENTER_SHORT"`
- `expectancy_check_v1` with `planned_r_multiple: 2.5`, `breakeven_win_rate_required: 0.2857`
- `learning_record_candidate_v1`
- Stop = 1.6× ATR14, Target = 4.0× ATR14 (from your `config_v0.1.yaml`)

Validate after adding:
```bash
python3 training/validate_agentic_corpus_v1.py training/corpus_v05_agentic_seed.jsonl
```

That is all. Do not wait for me. Do not touch `prove_learning/`.

---

## What I will provide when the operator says to merge

A validated JSONL file with 286 gold examples from real SOL-PERP decisions — entries, stand-downs, and INSUFFICIENT_DATA rows — in correct `finquant_agentic_qa_v1` format. The operator will hand it to you. You append it and validate. That's the merge point.

Until then: your scope, my scope, separate.

— Cody
