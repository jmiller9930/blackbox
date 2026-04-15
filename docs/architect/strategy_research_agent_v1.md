# Strategy Research Agent (SRA) — architectural role

**Status:** Normative — first-class role for **Quant Research Kitchen V1** (not a full implementation in v1).  
**Short form:** SRA (internal only).

---

## 1. Purpose

The **Strategy Research Agent** is the governed **research conductor** for the kitchen: she operates the platform **on behalf of** the human operator using the **same rules** as everyone else. She is **not** the strategy; she **assembles manifests**, **launches approved experiments**, **reads artifacts**, **compares to baseline**, and **recommends** next steps for **human approval**.

This document exists so the platform is built with **stable interfaces** for her **before** autonomous wiring — avoiding architectural rework later.

---

## 2. Allowed capabilities (target)

The SRA must eventually be able to:

| Area | Capability |
|------|------------|
| **Baseline** | Read active baseline tag, commit hint, deterministic metrics, Monte Carlo reference presence, report paths |
| **Registry** | Read [`renaissance_v4/registry/catalog_v1.json`](../../renaissance_v4/registry/catalog_v1.json) — **approved modules only** |
| **Manifest** | Create and edit **candidate** manifests, run [`renaissance_v4/manifest`](../../renaissance_v4/manifest/) validation before submission |
| **Experiments** | Submit jobs via the same governed paths as the UI (`POST` experiment jobs), poll queue, fetch experiment detail and exports |
| **Analysis** | Consume deterministic + Monte Carlo summaries, comparison vs baseline, classification **improve / degrade / inconclusive** (aligned with existing recommender semantics where applicable) |
| **Recommendation** | Emit **structured** artifacts for review (see §6) — **recommendation**, not promotion |

---

## 3. Prohibited actions (hard limits)

The SRA **must not**:

- Silently mutate the **locked baseline** or baseline code paths
- Bypass **deterministic replay**, **Monte Carlo**, or required **artifact** generation
- **Self-promote** a candidate to baseline (promotion remains **human / architect** process)
- Edit **production code** via the workbench or inject **arbitrary code** from prompts
- Operate outside **approved manifests**, **catalog** entries, and **governed experiment types**

**Rule:** *Recommendation is allowed. Promotion without approval is not.*

---

## 4. Required interfaces (stable for automation)

These must remain stable so the SRA can integrate without one-off scrapers:

| Interface | Purpose |
|-----------|---------|
| **Registry layer** | Read-only access to factor / signal / regime / risk / fusion / execution entries in `catalog_v1.json` |
| **Manifest layer** | `strategy_manifest_v1` JSON + validation API (`python -m renaissance_v4.manifest …` or future HTTP mirror) |
| **Experiment layer** | `GET/POST /api/v1/renaissance/jobs`, `GET …/experiments`, `GET …/experiments/<id>`, export URLs in detail payload |
| **Baseline layer** | `GET /api/v1/renaissance/baseline`, file downloads via `GET /api/v1/renaissance/file?rel=…`, baseline CSV exports |
| **Recommendation layer** | Structured artifacts (§6); human approval boundary before any baseline promotion |

Future: optional **read-only** `GET /api/v1/renaissance/registry` mirroring the catalog JSON — add when agent wiring starts; file-based catalog is sufficient for v1 positioning.

---

## 5. Approval boundary

| Stage | Who decides |
|-------|-------------|
| **Experiment run** | Governed job + manifest validity (system + operator policy) |
| **Recommendation** | SRA may emit **promote_candidate / reject_candidate / rerun_needed / inconclusive** as **advisory** |
| **Promotion to baseline** | **Human / architect** — never automatic from SRA or UI |

---

## 6. Artifact model (reserved types)

Durable, traceable artifacts (JSON or Markdown v1). Suggested storage root: `renaissance_v4/state/agent_artifacts/` (see README there).

| Type | Role |
|------|------|
| **agent_manifest_request** | Intent to assemble or change a candidate manifest (inputs, module picks) |
| **agent_experiment_submission** | Record of job submission (job id, action, experiment id, timestamps) |
| **agent_result_summary** | Structured digest of deterministic + Monte Carlo + paths after completion |
| **agent_promotion_recommendation** | Advisory recommendation with candidate id, baseline reference, comparison summary, risk notes, status enum |

Example recommendation shape: [`renaissance_v4/configs/agent_artifacts/example_agent_promotion_recommendation.json`](../../renaissance_v4/configs/agent_artifacts/example_agent_promotion_recommendation.json).

---

## 7. Governance model

The SRA is subject to the same rules as the rest of **Quant Research Kitchen V1**:

- Locked baseline **immutable**
- Experiments **reproducible**, outputs **artifact-backed**
- Recommendations **reviewable**
- No recommendation becomes **truth** without **human-approved** promotion

**The SRA is an accelerator, not an override.**

---

## 8. Version 1 position

v1 **does not** require full autonomous SRA behavior. v1 **does** require:

- This role documented as **first-class**
- Manifest + experiment APIs designed for **programmatic** use
- Artifact locations and types **reserved**
- No architectural change required later **only** to “add the agent”

---

## 9. Foundation — hypothesis + experiment loop (Phase 1, DV-ARCH-SRA-FOUNDATION-030)

Structured inputs and durable traceability **without** ML or feedback loops:

| Artifact | Role |
|----------|------|
| [`renaissance_v4/state/hypotheses.jsonl`](../../renaissance_v4/state/hypotheses.jsonl) | Append-only hypotheses (`hypothesis_id`, `description`, `parameters`, `created_at`, `created_by`). Manual JSON is OK; see [`hypotheses.example.jsonl`](../../renaissance_v4/state/hypotheses.example.jsonl). |
| [`renaissance_v4/state/hypothesis_results.jsonl`](../../renaissance_v4/state/hypothesis_results.jsonl) | One line per run: `hypothesis_id`, `experiment_id`, `strategy_id`, `classification`, `key_metrics`, `timestamp`, plus `manifest_path_repo` when applicable. |

**Manifest generation:** `renaissance_v4.research.sra_foundation.generate_manifest_from_hypothesis` merges `parameters` onto the locked [`baseline_v1_recipe.json`](../../renaissance_v4/configs/manifests/baseline_v1_recipe.json) template and validates against [`catalog_v1.json`](../../renaissance_v4/registry/catalog_v1.json) (deterministic for identical hypothesis records).

**Execution:** `python -m renaissance_v4.research.sra_foundation run <hypothesis_id>` writes `configs/manifests/sra_*_*.json` and invokes the existing **`compare-manifest`** pipeline (full Kitchen flow). Does **not** modify ingestion (024-C) or evaluators.

**Controlled variants (DV-ARCH-SRA-VARIANTS-031):** `generate_variants_from_hypothesis(hypothesis_id, n_variants)` appends derived rows to `hypotheses.jsonl` with `parent_hypothesis_id`, `variant_type` (`signal_toggle` = drop one resolved signal, `mc_config_offset` = single Monte Carlo seed bump), and `variant_index`. One bounded change per variant; deterministic for the same base + N. CLI: `… sra_foundation variants <id> <N>`. Result lines in `hypothesis_results.jsonl` copy parent/variant fields for traceability.

---

## 10. Related

- Kitchen frame: [`quant_research_kitchen_v1.md`](quant_research_kitchen_v1.md)
- Modularity: [`quant_research_kitchen_modularity_v1.md`](quant_research_kitchen_modularity_v1.md)
- Agent registry (BlackBox bots): [`AGENTS.md`](../../AGENTS.md)
