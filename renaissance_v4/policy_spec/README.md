# PolicySpecV1 + normalization (DV-ARCH-CANONICAL-POLICY-SPEC-046)

## DV-063 — Canonical indicator vocabulary (frozen structure)

| Field | Answer |
|--------|--------|
| **RE:** | DV-ARCH-CANONICAL-POLICY-VOCABULARY-063 |
| **Where declarations live** | Top-level **`indicators`** on PolicySpecV1 (`policy_spec_v1.json`). Shape: `schema_version` (`policy_indicators_v1`), **`declarations`**, optional **`gates`**, optional **`notes`**. |
| **Frozen vocabulary** | `INDICATOR_KIND_VOCABULARY` in **`renaissance_v4/policy_spec/indicators_v1.py`** — includes EMA, SMA, RSI, ATR, MACD, Bollinger Bands, VWAP, Supertrend, Stochastic, ADX, plus CCI, Williams %R, MFI, OBV, Parabolic SAR, Ichimoku, Donchian, `volume_filter`, `divergence`, `body_measurement`, `fixed_threshold`, `threshold_group`. |
| **Per-indicator parameters** | Each declaration is `{ "id": "<unique>", "kind": "<vocabulary>", "params": { ... } }`. Params are validated **only** for declared `kind` (see `indicators_v1._validate_params_for_kind`). |
| **Thresholds / gates** | Optional **`indicators.gates`**: `{ "indicator_id": "<declaration id>", "operator": "<lt|lte|gt|gte|eq|between|cross_above|cross_below>", "value": <number or [a,b]>, "reference_indicator_id": "..." }`. Gates reference `declarations[].id` only. |
| **Validation** | **Declared** kinds must be in the frozen set and params must match the kind. **Undeclared** kinds are not validated. **Empty** `declarations` is valid. Unknown keys under `indicators` are rejected. Implementation: `validate_indicators_section()`. |
| **Harness** | Intake sets **`RV4_POLICY_INDICATORS_JSON`** for the Node process; **`run_ts_intake_eval.mjs`** echoes **`policy_indicators`** on the harness JSON line (structure mirror + kind set). |

## DV-064 — Indicator mechanics (end-to-end)

| Field | Answer |
|--------|--------|
| **RE:** | DV-ARCH-INDICATOR-MECHANICS-064 |
| **Mechanical registry** | **`MECHANICAL_CLASS_BY_KIND`** in **`renaissance_v4/policy_spec/indicator_mechanics.py`**. |
| **Intake failure text** | **`indicator_declared_but_not_mechanically_supported: \<kind\>`** when a declared kind is not `mechanically_supported`. |
| **Harness** | **`indicator_engine.mjs`** computes series from synthetic OHLCV; **`run_ts_intake_eval.mjs`** passes **`ctx.indicators`** as the optional 5th argument to **`generateSignalFromOhlc`**. |
| **Extension** | Add vocabulary + params + class + **`indicator_engine.mjs`** implementation — PolicySpecV1 **`indicators`** shape unchanged. |

## Response header (046)

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
