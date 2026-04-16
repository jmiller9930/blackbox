# Quant Research Kitchen — completed checklist (Renaissance)

**Location:** This file lives under `renaissance_v4/` so the checklist stays next to the validation engine.  
**Update when:** A directive closes, a major harness feature ships, or LOAD-028 inventory changes.

---

## Completed (product / engine)

- [x] **Architecture & naming** — `docs/architect/quant_research_kitchen_v1.md`, `quant_research_kitchen_modularity_v1.md`, SRA role `strategy_research_agent_v1.md`.
- [x] **Workbench v1 (dashboard)** — Route `/dashboard.html#/renaissance`, baseline + experiments + exports + approved jobs — see `renaissance_v4/WORKBENCH_V1.md` (“Version 1 scope delivered”).
- [x] **Workbench APIs** — Documented in `WORKBENCH_V1.md` (`/api/v1/renaissance/*`).
- [x] **Harness** — `research/robustness_runner.py`: `export-trades`, `baseline-mc`, `compare`, `compare-manifest`, `ingest-policy` (full pipeline per DV-ARCH-POLICY-INGESTION-024-C; see `docs/architect/DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md` §13).
- [x] **Manifest-driven replay (v7.2)** — `research/replay_runner.py` + `configs/manifests/baseline_v1_recipe.json`; `MANIFEST_REPLAY_INTEGRATION.md`.
- [x] **Policy package replay (024-A)** — `research/policy_package_ingest.py`.
- [x] **SRA plumbing** — `research/sra_foundation.py`, variants/runs, experiment index — see `state/` artifacts and tests under repo `tests/`.
- [x] **Governance docs** — LOAD-028 (rule documented), INTAKE-021, `blackbox_policy_kitchen_integration_writeup.md`, `policy_package_standard.md`.
- [x] **Policy wiring map (029)** — `docs/architect/policy_wiring_surface_map_v1.md` (complete per that doc).
- [x] **Jupiter MC2 + API (039)** — `docs/validation/DV-ARCH-JUPITER-MC2-039.md` (complete).
- [x] **Automated regression (target suites)** — See `docs/validation/stabilization_035_report.md` §1 for pytest bundles run against this stack (not a substitute for full operational cycles).

---

## Validation directives (explicit outcomes)

| Directive | Outcome | Evidence |
|-----------|---------|----------|
| DV-ARCH-JUPITER-MC2-039 | **Complete** | `docs/validation/DV-ARCH-JUPITER-MC2-039.md` |
| DV-ARCH-STABILIZATION-035 (full 5 cycles) | **Not met** | `docs/validation/stabilization_035_report.md` |
| DV-ARCH-JUPITER-MC-UNBLOCK-040 | **Not met** | Same report, §9 |

---

## Open / not done (tracked elsewhere)

- [ ] **LOAD-028 implementation** — Persisted submission → `approved_for_activation`, unified package submit, MC/compare tied to submission id — see LOAD-028 §13 “still open”.
- [ ] **Stabilization / MC unblock** — Non-empty native closed-trade PnL where required (`baseline-mc` / Sean ledger); see `stabilization_035_report.md` and §9 (040).

---

## Related paths

| Path | Role |
|------|------|
| `renaissance_v4/WORKBENCH_V1.md` | Product spec + API list |
| `renaissance_v4/ROBUSTNESS.md` | Robustness runner usage |
| `docs/validation/` | Directive closure and smoke evidence |
| `policies/generated/renaissance_baseline_v1_stack/` | Generated baseline stack artifacts |
