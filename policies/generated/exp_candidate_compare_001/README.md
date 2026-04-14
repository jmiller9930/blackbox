# Generated policy package — `exp_candidate_compare_001`

**Manifest:** `renaissance_v4/configs/manifests/candidate_robustness_compare.json`

**Generator:** DV-ARCH-POLICY-GENERATOR-022-C (`generator_version=022-c-1`)

## Validate

```bash
export PYTHONPATH=.
python3 scripts/validate_policy_package.py policies/generated/exp_candidate_compare_001
```

## Parity

```bash
python3 scripts/verify_generated_policy_parity_022c.py --package exp_candidate_compare_001
```

## Module

- `jupiter_4_exp_candidate_compare_001_policy.py` — `replay_manifest_policy_checksum()`, `evaluate_jupiter_4_manifest_policy()`

Authoritative replay uses `run_manifest_replay` (same engine as `replay_runner`).
