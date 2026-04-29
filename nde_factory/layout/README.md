# NDE Factory — host data root (`/data/NDE`)

**NDE** = **Narrow Domain Expert**: a narrow-domain model/adapter trained for a bounded mission (verification, guided reasoning), not a general assistant.

## Layout rules

- Each domain lives in **isolation** under `/data/NDE/<domain>/`.
- **Datasets** are domain-local (`datasets/`).
- **Source manifests** are domain-local (`sources/manifests/`).
- **Training scripts** (domain generators, configs) are domain-local (`training/`).
- **Eval harnesses** and eval artifacts are domain-local (`evals/`).
- **Adapters** and **exported models** are domain-local (`adapters/`, `models/`).
- **Reports** and **runs** (registry-style logs) are domain-local (`reports/`, `runs/`).

A future **control plane** may orchestrate jobs across domains; it **must not** mix artifacts between domains (no shared mutable dataset roots without explicit promotion/copy contracts).

## Domains in this tree

| Domain | Purpose (summary) |
|--------|-------------------|
| `finquant/` | **NDE: FinQuant** — quant-finance verifier pipeline (legacy host: `/data/finquant-1/` until migration). |
| `secops/` | **NDE: SecOps** — compliance/security verification-oriented dataset and training prep (CMMC-first). |

## Deploy

Canonical files live in the repo under `nde_factory/layout/`. On the training server, run:

```bash
# from repo root, on the host that owns /data
sudo bash scripts/install_nde_data_layout.sh /data/NDE
```

After install, this content lives at **`/data/NDE/README.md`** on the training server.
