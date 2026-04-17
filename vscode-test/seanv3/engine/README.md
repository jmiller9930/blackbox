# `engine/` — execution layer helpers (not policy strategy)

This directory holds code the **Sean execution engine** uses **without** embedding Kitchen policy strategy.

## What belongs here

- **Artifact loading** — `artifact_policy_loader.mjs`: resolves manifest binding → `evaluator.mjs` under `renaissance_v4/state/policy_intake_submissions/<submission_id>/artifacts/`.
- **Shared non-strategy math** — e.g. `atr_math.mjs` (indicators as mechanics, not a trading strategy).

## What must not be added here

- Strategy rules, entry/exit “edge” logic, or named policy modules (those live in **Kitchen-built artifacts** or under `legacy_policies/` for quarantine/tests only).

## Normative contract

See **`docs/architect/engine_policy_demarcation_v1.md`**.

## CI

`test/engine_policy_boundary_guard.test.mjs` guards the runtime hot path against `legacy_policies` imports.
