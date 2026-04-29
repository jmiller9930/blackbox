# Source → concepts → training — mandatory policy (v0.1)

**Status:** Mandatory for all NDE training data  
**Applies to:** FinQuant, SecOps, and **all future NDE domains**  
**Effective:** Policy version v0.1 — datasets promoted to training **after** this policy must comply; legacy artifacts require migration plan before further training promotion.

---

## 1. Purpose

No NDE dataset may be **trained from hand-written examples alone**. Training JSONL must trace to **authoritative sources** through a reproducible pipeline:

```text
source → raw → extracted → concepts → staging JSONL → proof → training
```

Hand-authored rows are **not** forbidden as *material*, but they **cannot** be the sole origin of a dataset used for training without upstream source linkage.

---

## 2. Required host layout (per domain)

Each domain `<domain>` (e.g. `finquant`, `secops`) **must** maintain:

```bash
/data/NDE/<domain>/sources/raw/
/data/NDE/<domain>/sources/extracted/
/data/NDE/<domain>/sources/concepts/
/data/NDE/<domain>/datasets/staging/
/data/NDE/<domain>/reports/
```

Cross-domain policy and governance docs:

```bash
/data/NDE/reports/
```

Install from repo: `scripts/install_nde_data_layout.sh` seeds `/data/NDE/` from `nde_factory/layout/`.

---

## 3. Approved source types

| Category | Examples | Notes |
|----------|----------|--------|
| **Regulatory / framework** | CMMC, NIST SP 800-171/172, CIS Controls summaries | Prefer official PDF/HTML **downloads** recorded in a manifest |
| **Vendor / exchange technical** | Exchange API docs, fee schedules, liquidation/mark specs | Version URL + capture date |
| **Standards bodies** | IEEE, ISO refs where license permits | Citation + excerpt checksum |
| **Curated datasets** | Licensed market data, CVE/NVD feeds | License ID + retrieval manifest |
| **Internal authoritative** | Signed policy PDFs, architecture baselines | Document ID + hash |

**Not approved** as sole authority: anonymous forums, unverifiable blogs, model-generated text **without** grounding in an approved source-derived concept record.

---

## 4. Extraction process

1. **Ingest:** Copy or download into `sources/raw/` with immutable naming (`{source_id}_{version}_{sha256_short}.pdf` or equivalent).
2. **Register:** Append/update `sources/manifests/` entry (URL, hash, date, license).
3. **Extract:** Produce structured text/tables JSON or Markdown chunks in `sources/extracted/` keyed by `source_id` + segment IDs.
4. **Normalize:** Map excerpts to **concept records** (see §5); store under `sources/concepts/`.
5. **Version:** Any change to extraction logic bumps extractor version in reports.

---

## 5. Concept schema (minimum)

Each concept record **should** be JSON (one file or JSONL) with at least:

| Field | Description |
|-------|-------------|
| `concept_id` | Stable ID (e.g. `cmmc-practice-ac-l2-mfa`) |
| `source_ids` | List of `{ "source_id", "segment_id" }` proving derivation |
| `title` | Short label |
| `claims[]` | Normalized statements suitable for verifier prompts |
| `control_refs[]` | Optional framework IDs (e.g. AC-2, AU-2, IA-5) |
| `risk_notes` | Misinterpretations / traps for adversarial pairing |
| `extractor_version` | Semver or git hash |

Concepts are the **only** approved anchors for synthetic/adversarial expansion (§8).

---

## 6. Training row schema (minimum)

Every JSONL row **must** include:

| Field | Required | Description |
|-------|----------|-------------|
| `instruction` | Yes | Task instructions |
| `input` | Yes | Prompt / claim to verify |
| `output` | Yes | Reference verifier answer |
| `source_ids` | **Yes** | List of `{ "source_id", "concept_id"? , "segment_id"? }` tracing rationale |

Optional: `category`, `adversarial`, `quality_flags`, `generator_version`.

Rows **without** `source_ids` are **invalid for training promotion**.

---

## 7. Source traceability requirement

- **Primary rows:** `source_ids` MUST point to real segments from `sources/extracted/` (via concepts).
- **Synthetic / adversarial rows:** MUST include at least one `concept_id` from `sources/concepts/` that defines the misconception or trap; MAY add `synthetic: true` in metadata **only** alongside that linkage.

Traceability is proven by:

1. Manifest exists for each `source_id`.
2. Concept file lists `source_ids` consistent with manifests.
3. Build report lists mapping from row index → `source_ids` / `concept_id`.

---

## 8. Adversarial generation rules

| Rule | Requirement |
|------|-------------|
| Grounding | Every adversarial/trap row derives from a **concept** `risk_notes` or explicit negation of a sourced claim |
| No orphan traps | No arbitrary false claims without a concept anchor |
| Labeling | `adversarial: true` + `quality_flags` including `concept_derived` recommended |
| Diversity | Paraphrase variants OK; core falsity must match documented trap |

---

## 9. Quality gates (before staging promotion)

| Gate | Check |
|------|--------|
| **G1** | All `source_ids` resolve via manifest |
| **G2** | Extracted checksums match raw files |
| **G3** | Concept coverage matrix vs training objectives (report) |
| **G4** | Row count, adversarial ratio, schema validation (CI or script) |
| **G5** | No empty `source_ids` |

---

## 10. Proof requirements before training

Training **must not** start from staging alone without:

1. **`reports/dataset_build_report_{version}.md`** — sources list, hashes, extractor version, row counts.
2. **`reports/concept_coverage_{version}.md`** — matrix: concepts → row ranges.
3. **`reports/staging_validation.json`** (or equivalent) — automated schema pass, `source_ids` presence.

Operator/architect sign-off per domain governance.

---

## 11. Domain applicability

| NDE | Policy |
|-----|--------|
| **SecOps** | Mandatory for new builds; v0.1 hand-generated CMMC-style JSONL in repo is **legacy** until rebuilt through extraction + concepts + provenance |
| **FinQuant** | Mandatory for `/data/NDE/finquant/` path; legacy `/data/finquant-1/` datasets require migration or explicit waiver document in `/data/NDE/reports/` |
| **Future domains** | Mandatory from first training drop |

---

## 12. Related repo pointers

- NDE layout: `nde_factory/layout/README.md`
- Install script: `scripts/install_nde_data_layout.sh`

**Default rule:** *Source extraction → concepts → staging JSONL → proof → training* is the **only** approved path for **new** NDE training data after this policy revision.
