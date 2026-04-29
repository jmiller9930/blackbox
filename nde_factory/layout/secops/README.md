# NDE: SecOps — domain folder (`/data/NDE/secops`)

## Domain purpose

**NDE: SecOps** targets a narrow **compliance and security operations** expert: verification-style reasoning over policy text, controls mapping, vulnerability awareness (CVE/KEV context), and frameworks (NIST, CIS, FedRAMP) **within bounded missions** — not unconstrained security advice.

## Source strategy

**Mandatory pipeline:** `/data/NDE/reports/source_to_training_policy_v0.1.md` — SecOps training JSONL must be driven by **source → raw → extracted → concepts → staging → proof → training** (no training promotion from hand-written-only rows).

- **Primary hub:** CMMC Resources & Documentation (DoD CIO), declared in `sources/manifests/source_manifest_v0.1.json`.
- **Planned augmentations:** authoritative APIs and frameworks (NVD CVE API, CISA KEV, MITRE ATT&CK, NIST CSF, NIST SP 800-171/172, FedRAMP, CIS Benchmarks where licensing permits).
- Raw downloads under `sources/raw/`; normalized extracts under `sources/extracted/`; structured concepts under `sources/concepts/`. Every staging row **must** include **`source_ids`** tied to extracted segments or concept IDs.

## Dataset strategy

- Deterministic staging JSONL under `datasets/staging/`; promoted/final drops under `datasets/final/`.
- Quality gates and adversarial/trap cases per `reports/secops_dataset_build_plan_v0.1.md`.

## Training target

A SecOps-oriented verifier adapter trained on approved JSONL; generator entrypoint (planned): `training/cmmc_source_to_training.py` (not implemented until approved).

## Eval criteria

Eval categories and pass thresholds defined in the dataset build plan; harness placement under `evals/` when implemented.

## Runtime role

Domain-local data plane for SecOps NDE; no cross-domain mixing with FinQuant artifacts.

## Current status

**v0.1 — structure and planning only.** Directory tree, source manifest seed, and build plan are in place. **No full extraction or training** unless explicitly approved.
