# Renaissance Baseline V1 — generated policy package (022-B)

**Source manifest:** `renaissance_v4/configs/manifests/baseline_v1_recipe.json`

## Files

| File | Role |
|------|------|
| `jupiter_4_renaissance_baseline_v1_policy.py` | `replay_baseline_v1_checksum()` delegates to `run_manifest_replay`; `evaluate_jupiter_4_renaissance_baseline_v1` returns `Jupiter4SeanPolicyResult` (placeholder for single-tick bridge). |
| `POLICY_SPEC.yaml` | Identity + parity pointers. |
| `INTEGRATION_CHECKLIST.md` | Required by `validate_policy_package.py`. |

## Validate

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 scripts/validate_policy_package.py policies/generated/renaissance_baseline_v1
```

## Parity (VALIDATION_CHECKSUM)

Requires `renaissance_v4/data/renaissance_v4.sqlite3` (or equivalent DB path used by `get_connection()`).

```bash
export PYTHONPATH=.
python3 scripts/verify_policy_022b_parity.py
```

Or manually:

```bash
python3 -m renaissance_v4.research.replay_runner 2>&1 | grep VALIDATION_CHECKSUM
python3 -c "from policies.generated.renaissance_baseline_v1.jupiter_4_renaissance_baseline_v1_policy import replay_baseline_v1_checksum; print('[VALIDATION_CHECKSUM]', replay_baseline_v1_checksum())"
```

The checksum line must match exactly.

## Non-goals (022-B)

No generalized generator, no UI, no activation — **PoC only** (see directive DV-ARCH-POLICY-GENERATOR-022-B).
