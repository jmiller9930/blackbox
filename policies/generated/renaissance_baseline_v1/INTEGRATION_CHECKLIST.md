# Integration checklist — `renaissance_baseline_v1` (022-B PoC)

**Package path:** `policies/generated/renaissance_baseline_v1/`

This is a **research / parity** package: it wires the Kitchen baseline manifest to the same `run_manifest_replay` entrypoint used by `replay_runner`. It is **not** a new live baseline Jupiter slot unless engineering extends `VALID_BASELINE_JUPITER_POLICY_SLOTS` and the ledger bridge.

## Mechanical validation

- [x] `python3 scripts/validate_policy_package.py policies/generated/renaissance_baseline_v1`

## Ledger / slot (optional — not done for 022-B)

- [ ] Add slot constant + `VALID_BASELINE_JUPITER_POLICY_SLOTS` if this policy should be operator-selectable.
- [ ] Extend `signal_mode_for_baseline_policy_slot` / labels if wired.

## Evaluator / bridge

- [x] Canonical Python: `jupiter_4_renaissance_baseline_v1_policy.py`
- [ ] Wire `sean_jupiter_baseline_signal` (or successor) only if live evaluation is required — **022-B does not require this.**

## Proof

- [x] Parity: `replay_baseline_v1_checksum()` matches `run_manifest_replay` for `baseline_v1_recipe.json` (see `scripts/verify_policy_022b_parity.py`).
