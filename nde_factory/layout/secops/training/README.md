# SecOps — training scripts (`/data/NDE/secops/training`)

Domain-local generators and training configs live here.

## Mandatory driver

Training data generation **must** follow **`source → raw → extracted → concepts → staging JSONL → proof → training`** per `/data/NDE/reports/source_to_training_policy_v0.1.md`. Generators consume **concepts** under `sources/concepts/` (not hand-written-only exemplars).

## Planned

| Script | Purpose |
|--------|---------|
| `cmmc_source_to_training.py` | Pipeline entry: manifests + extracted sources → concepts registry → staging JSONL with **`source_ids`** → proof artifacts (implement per policy). |

No training subprocess is started by files in this folder until operators explicitly run approved tooling **and** proof gates in the policy are satisfied.
