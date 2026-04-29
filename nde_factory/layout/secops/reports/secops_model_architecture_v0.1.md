# SecOps NDE — model architecture (v0.1)

**Status:** Architecture lock — **no training executed** under this document until explicitly approved.

## Base model

| Field | Value |
|-------|--------|
| **Model ID** | `Qwen/Qwen2.5-1.5B-Instruct` |
| **Role** | Lightweight **SecOps verifier** (instruction-following, four-part verifier format aligned with staging JSONL `instruction` / `input` / `output`). |
| **Adaptation** | **QLoRA / LoRA** on top of the quantized base (same stack pattern as FinQuant: 4-bit load + PEFT LoRA). |

## Why 1.5B is sufficient for SecOps

- **Task shape:** Verifier rows are structured (short claims, checklist-style `DATA evidence required`, PASS/FAIL labels). They reward **format adherence and grounded hedging** more than open-ended finance reasoning.
- **Footprint:** SecOps runs **more often** and with **lower GPU budget** than FinQuant; a **1.5B** instruct model keeps latency and VRAM small on the same host class (e.g. trx40-class workstation).
- **Dataset scale:** Initial **NIST-only** staging is bounded (~400 smoke-oriented rows, larger concept pool); a compact base avoids overfitting noise while LoRA specializes style and schema.
- **Escalation path:** If eval shows systematic weakness, policy allows moving to a larger Qwen2.5 instruct variant **without changing** the source → concepts → staging pipeline.

## Dataset source rule (mandatory)

All training/eval JSONL **must** be produced through the locked pipeline:

**source files → extracted text → concept cards (`source_ids`) → staging JSONL → proof/report**

See `/data/NDE/reports/source_to_training_policy_v0.1.md` and `nde_source_processor.py`. No hand-authored staging rows for production promotion.

**Current authoritative staging (NIST-only, v0.3 naming):**

`/data/NDE/secops/datasets/staging/secops_nist_v0.3_from_sources.jsonl`

CMMC/CIS PDFs remain **operator-supplied** until manually placed under `sources/raw/` and reprocessed.

## Artifact paths

| Artifact | Path |
|----------|------|
| **Training config** | `/data/NDE/secops/training/config_secops_qwen1_5b_v0.1.yaml` |
| **Adapter output (production target)** | `/data/NDE/secops/adapters/secops-qwen2.5-1.5b-v0.1` |
| **Adapter output (smoke first run)** | `/data/NDE/secops/adapters/secops-qwen2.5-1.5b-v0.1-smoke` |
| **Eval report (post-training)** | `/data/NDE/secops/reports/secops_v0.1_eval_report.md` |
| **Training process reports** | Same pattern as FinQuant: smoke/full markdown under `/data/NDE/secops/reports/` when `train_qlora.py` is run (see FinQuant training docs). |

## Training process (mirrors FinQuant)

Same software stack and **`train_qlora.py`** contract as FinQuant (`finquant/training/train_qlora.py`): YAML config, 4-bit quantization, LoRA, `SFTTrainer`, staging JSONL with `instruction` / `input` / `output`.

**Only differences:** SecOps **`FINQUANT_BASE`** is set to the SecOps tree (reuse of the script name is historical):

```bash
export FINQUANT_BASE=/data/NDE/secops
python3 finquant/training/train_qlora.py smoke \
  --config /data/NDE/secops/training/config_secops_qwen1_5b_v0.1.yaml \
  --base /data/NDE/secops
```

Install training deps on the GPU host: `pip install -r finquant/requirements-finquant-training.txt` (unchanged stack).

**No training** until operators explicitly run the command above (or equivalent) after CMMC/CIS scope is decided.

## Governance

- **FinQuant:** unchanged; no shared adapter paths.
- **Runtime integration** (APIs, gateways): out of scope until eval sign-off.
