# Source processor report — secops

**Generated:** `2026-04-29T18:24:03Z` UTC
**NDE root:** `/Users/bigmac/Documents/code_projects/blackbox/nde_factory/layout`
**Domain:** `secops`
**Config:** `/Users/bigmac/Documents/code_projects/blackbox/nde_factory/layout/secops/domain_config.yaml`

## Summary

| Metric | Value |
|--------|-------|
| Raw files processed (extracted non-empty) | 1 |
| Concept segments | 1 |
| Staging rows | 150 |
| Adversarial (target ratio 0.70) | 105 |
| Non-adversarial | 45 |

## Outputs

- **Extracted:** `/Users/bigmac/Documents/code_projects/blackbox/nde_factory/layout/secops/sources/extracted`
- **Concepts:** `/Users/bigmac/Documents/code_projects/blackbox/nde_factory/layout/secops/sources/concepts/concepts_v0.1.jsonl`
- **Staging:** `/Users/bigmac/Documents/code_projects/blackbox/nde_factory/layout/secops/datasets/staging/secops_v0.1.jsonl`

## Source traceability

Every staging row includes `source_ids` with `concept_id`, `source_id`, and `segment_id`.

## Warnings

- .gitkeep: skipped extension .

## Policy

Build aligns with `source_to_training_policy_v0.1.md` (concepts + provenance). Training not run.
