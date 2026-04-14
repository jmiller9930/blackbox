# INTEGRATION_CHECKLIST — `renaissance_baseline_v1_stack`

**022-C generated package** — `policies/generated/renaissance_baseline_v1_stack/`

## Mechanical

- [x] `python3 scripts/validate_policy_package.py policies/generated/renaissance_baseline_v1_stack`

## Live BlackBox wiring (optional)

- [ ] Slot + bridge only if this policy should be operator-selectable as a Jupiter baseline.

## Proof

- [x] Parity: `python3 scripts/verify_generated_policy_parity_022c.py --package renaissance_baseline_v1_stack`
