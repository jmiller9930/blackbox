# Generated policy package — `renaissance_baseline_v1_stack`

**Manifest:** `renaissance_v4/configs/manifests/baseline_v1_recipe.json`

**Generator:** DV-ARCH-POLICY-GENERATOR-022-C (`generator_version=022-c-1`)

## Validate

```bash
export PYTHONPATH=.
python3 scripts/validate_policy_package.py policies/generated/renaissance_baseline_v1_stack
```

## Parity

```bash
python3 scripts/verify_generated_policy_parity_022c.py --package renaissance_baseline_v1_stack
```

## Module

- `jupiter_4_renaissance_baseline_v1_stack_policy.py` — `replay_manifest_policy_checksum()`, `evaluate_jupiter_4_manifest_policy()`

Authoritative replay uses `run_manifest_replay` (same engine as `replay_runner`).
