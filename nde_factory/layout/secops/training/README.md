# SecOps — training scripts (`/data/NDE/secops/training`)

Domain-local generators and training configs live here.

## Mandatory driver

Training data generation **must** follow **`source → raw → extracted → concepts → staging JSONL → proof → training`** per `/data/NDE/reports/source_to_training_policy_v0.1.md`. Generators consume **concepts** under `sources/concepts/` (not hand-written-only exemplars).

## Planned

| Script | Purpose |
|--------|---------|
| `cmmc_source_to_training.py` | Pipeline entry: manifests + extracted sources → concepts registry → staging JSONL with **`source_ids`** → proof artifacts (implement per policy). |

## SecOps Qwen 1.5B (v0.1)

| File | Purpose |
|------|---------|
| `config_secops_qwen1_5b_v0.1.yaml` | QLoRA YAML for **`Qwen/Qwen2.5-1.5B-Instruct`**; staging: `datasets/staging/secops_nist_v0.3_from_sources.jsonl`. |
| `../reports/secops_model_architecture_v0.1.md` | Architecture lock (paths, rationale, FinQuant-parity training invocation). |

Smoke/full training uses **`finquant/training/train_qlora.py`** with **`FINQUANT_BASE=/data/NDE/secops`** and `--base /data/NDE/secops` — see architecture doc. **No training** until explicitly run on a CUDA host.

No training subprocess is started by files in this folder until operators explicitly run approved tooling **and** proof gates in the policy are satisfied.
