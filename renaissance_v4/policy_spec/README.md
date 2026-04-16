# PolicySpecV1 + normalization (DV-ARCH-CANONICAL-POLICY-SPEC-046)

## Response header

| Field | Value |
|-------|--------|
| **RE:** | DV-ARCH-CANONICAL-POLICY-SPEC-046 |
| **STATUS** | **partial** — schema + normalization + `jup_pipeline_proof_v1` implemented; **lab proof** for trades / MC still required on primary host |

## Audit: what existed before 046

| Asset | Role |
|-------|------|
| `docs/architect/policy_package_standard.md` | Sean → BlackBox **package layout**, `POLICY_SPEC.yaml` minimum fields |
| `policies/generated/*/POLICY_SPEC.yaml` | Generated Kitchen packages |
| `renaissance_v4/research/policy_package_ingest.py` | Validate → replay → artifacts (024-A/C) |
| `scripts/validate_policy_package.py` | Mechanical package checks |
| `vscode-test/seanv3/jupiter_*_policy.mjs` | Runtime Jupiter evaluators (merged code, not dynamic upload) |

## What 046 added (this folder + code)

1. **`policy_spec_v1.py`** — Canonical dataclasses + `to_canonical_dict()` / `policy_spec_v1_validate_minimal()`.
2. **`normalize.py`** — `normalize_policy(input)` maps `POLICY_SPEC.yaml` load dicts and loose dicts into **one** PolicySpecV1-shaped output.
3. **`policy_spec_v1.schema.json`** — JSON Schema for the canonical shape (draft validation).
4. **`jupiter_pipeline_proof_policy.mjs` + runtime registration** — `jup_pipeline_proof_v1` selectable via `POST /api/v1/jupiter/active-policy` (same path as other slots).

## Gaps (honest)

| 046 requirement | Status |
|-----------------|--------|
| All policies converge to PolicySpecV1 in **every** runner path | **Partial** — normalization exists; **ingest-policy / replay** still primarily read raw `POLICY_SPEC.yaml`; wire canonical dict through evaluation jobs is **next**. |
| Backtest parity (JUPv3/v4/MC vs Sean divergence) | **Not** re-run under this commit; document deltas when Kitchen compares normalized specs side-by-side. |
| Kitchen UI “Submit Policy for Evaluation” only | **LOAD-028** partial — copy/API audit separate. |
| `sean_paper_trades` non-zero + MC unblocked | **Operational** — requires primary host with `jup_pipeline_proof_v1` active and lifecycle allowing closes; **not** proven in CI. |

## Operational next steps

1. Deploy SeanV3 image including `jupiter_pipeline_proof_policy.mjs` (Dockerfile + `.dockerignore` updated).
2. `POST` `{"policy":"jup_pipeline_proof_v1"}` with operator token; confirm `GET /api/v1/jupiter/policy`.
3. Observe `sean_paper_trades`; then run `robustness_runner` / `baseline-mc` on exported PnL when non-empty.
