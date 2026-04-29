# SecOps NDE — Dataset build plan v0.1

**Status:** Planning only — **no automated extraction or training** unless explicitly approved.  
**Domain:** `/data/NDE/secops/`  
**Manifest:** `sources/manifests/source_manifest_v0.1.json`

---

## 1. Source acquisition

- **Primary:** CMMC Resources & Documentation hub (DoD CIO) — authoritative policy and document links from `source_manifest_v0.1.json`.
- **Planned additions:** NVD CVE API, CISA KEV, MITRE ATT&CK, NIST CSF, NIST SP 800-171/172, FedRAMP, CIS Benchmarks (subject to licensing).
- **Mechanism:** Crawl/download scripts *not implemented in this milestone*; acquisition will record provenance (URL, retrieval time, hash) per artifact.

## 2. Raw storage

- Path: `sources/raw/` — immutable blobs as fetched (HTML, PDF, JSON per API).
- Naming: content-addressed or `{source_id}_{retrieval_utc}_{sha256_short}` as agreed when tooling lands.

## 3. Text extraction

- Path: `sources/extracted/` — normalized UTF-8 text (and tables where feasible) per document.
- Steps: format-specific extractors (PDF, HTML), deduplication, section boundaries preserved where useful for verifier prompts.

## 4. Concept extraction

- Path: `sources/concepts/` — structured slices (control IDs, CVE IDs, CMMC level references, framework clause pointers) suitable for JSONL row synthesis.
- Traceability: each concept links back to raw/extracted IDs.

## 5. Training JSONL generation

- Path: `datasets/staging/` → promotion to `datasets/final/`.
- **Planned generator:** `training/cmmc_source_to_training.py` (stub only until approved).
- Rows: verifier-shaped schema (instruction, context, expected verdict categories) aligned with SecOps eval rubric — **schema TBD** before first smoke generation.

## 6. Quality gates

- Deterministic manifests (hashes, row counts).
- Schema validation for every JSONL line.
- Leakage checks (no evaluation answers embedded in context fields).
- Minimum coverage per framework bucket before full training.

## 7. Adversarial / trap case generation

- **Hallucination traps:** demand citations when claims are unsupported by provided context.
- **Contradiction traps:** paired excerpts that conflict — model must flag inconsistency.
- **Scope traps:** questions outside CMMC/NIST/CISA scope — model must refuse or narrow per verifier contract.
- **Policy drift traps:** outdated control versions mixed with current — detect revision mismatch.

## 8. Eval categories

| Category | Description |
|----------|-------------|
| CMMC level mapping | Map scenarios to appropriate CMMC practices / maturity expectations. |
| Control interpretation | Short passages requiring correct paraphrase vs violation detection. |
| CVE / KEV relevance | Given CVE + context, severity/priority reasoning within policy. |
| Framework crosswalk | NIST 800-171 vs CSF alignment questions (bounded). |
| Refusal / abstain | Requests that must not receive overconfident compliance claims without evidence. |

Eval harness placement: `evals/` when implemented.

---

## Generator mechanism (planned)

- **Location:** `/data/NDE/secops/training/`
- **First script:** `cmmc_source_to_training.py` — CMMC hub–oriented path only in v0.1 scope; broader sources added after manifest approval.
