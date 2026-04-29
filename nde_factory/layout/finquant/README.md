# NDE: FinQuant — domain folder (`/data/NDE/finquant`)

## Domain purpose

**NDE: FinQuant** is the narrow quant-finance verifier aligned with FinQuant-1 architecture (see repo `finquant/docs/FinQuant-1_architecture.md`). This tree holds **domain-local** sources, datasets, training configs, evals, adapters, models, reports, and run registry data.

## Source strategy

**Mandatory pipeline:** See `/data/NDE/reports/source_to_training_policy_v0.1.md` (repo: `nde_factory/layout/reports/source_to_training_policy_v0.1.md`). FinQuant training data must flow **source → raw → extracted → concepts → staging JSONL → proof → training** — not hand-written-only datasets.

Legacy sources and acquisition rules still align with FinQuant-1 dataset planning (`finquant/reports/dataset_plan_v0.1.md` and related). Staging JSONL and manifests must use `sources/raw|extracted|concepts/` and `datasets/staging/` here once migration from the legacy `/data/finquant-1/` root is executed; new drops must satisfy **`source_ids`** on every row.

## Dataset strategy

- **Staging** under `datasets/staging/`, **frozen/final** under `datasets/final/`.
- Content-addressed manifests and hashes consistent with existing FinQuant proof scripts (mirrored here post-migration).

## Training target

QLoRA (or agreed stack) on the FinQuant verifier dataset; configs live under `training/` when populated.

## Eval criteria

Verifier-shaped eval harness (`eval_finquant`-style) — exact thresholds documented in domain reports per phase.

## Runtime role

Serves as the **data plane** for FinQuant adapter training and eval on this host; control-plane CLI may register runs under `runs/`.

## Current status

**Active FinQuant v0.1 work (Phase 6 training, adapters, proof)** currently lives under:

**`/data/finquant-1/`**

Do **not** move or repoint active training artifacts until Phase 6 training and eval close. **Migration or mirroring** into `/data/NDE/finquant/` is **explicitly deferred** until then. This folder establishes the **target layout** only.

## Directory map

| Path | Role |
|------|------|
| `sources/` | Raw, extracted, concepts, manifests |
| `datasets/staging` | Reproducible staging JSONL |
| `datasets/final` | Frozen dataset drops |
| `training/` | Domain training scripts and YAML |
| `evals/` | Eval suites and reports |
| `adapters/` | LoRA/adapter outputs |
| `models/` | Exported / merged artifacts as needed |
| `reports/` | Build and proof reports |
| `runs/` | Run registry (control plane) |
