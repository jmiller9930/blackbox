# Strategy idea file format (`strategy_idea_v1`)

Plain UTF-8 **text** (`.txt`). This is **not** free-form prose: unknown keys are rejected and the first content line must be the format header.

## Rules

1. Encoding: **UTF-8**.
2. First non-empty, non-comment line must be exactly: **`strategy_idea_v1`**
3. Lines starting with `#` are comments (ignored).
4. Blank lines are ignored.
5. Every other line is **`key: value`** (one key per line). Keys are **case-insensitive**; store them lowercase in your head.
6. **`signal_modules`** and **`disabled_signal_modules`** use **comma-separated** catalog ids on **one** line (spaces after commas are fine).
7. No duplicate keys. No keys outside the allowed list (you get an explicit error naming allowed keys).

## Required fields

| Key | Meaning |
|-----|--------|
| `strategy_id` | Stable id for this test (letters, digits, `_`, `-`). |
| `strategy_name` | Human-readable name. |
| `symbol` | e.g. `SOLUSDT` |
| `timeframe` | e.g. `5m` |
| `factor_pipeline` | Catalog id, e.g. `feature_set_v1` |
| `signal_modules` | Comma list of **catalog** signal ids (see `renaissance_v4/registry/catalog_v1.json`). |
| `regime_module` | e.g. `regime_v1_default` |
| `risk_model` | e.g. `risk_governor_v1_default` |
| `fusion_module` | e.g. `fusion_geometric_v1` |
| `execution_template` | e.g. `execution_manager_v1_default` |
| `stop_target_template` | e.g. `none` |
| `experiment_type` | e.g. `replay_full_history` (must be in catalog `allowed_experiment_types`) |

## Optional fields

`baseline_tag`, `notes`, `start_date`, `end_date`, `atr_stop_mult`, `atr_target_mult`,  
`fusion_min_score`, `fusion_max_conflict_score`, `fusion_overlap_penalty_per_extra_signal`,  
threshold overrides (`mean_reversion_fade_min_confidence`, `trend_continuation_min_confidence`, …),  
`disabled_signal_modules` (comma list; each id must appear in `signal_modules`).

## Minimal example (copy and edit)

```
strategy_idea_v1

strategy_id: my_sme_test_v1
strategy_name: SME baseline copy with one signal dropped
symbol: SOLUSDT
timeframe: 5m
factor_pipeline: feature_set_v1
signal_modules: trend_continuation, pullback_continuation, breakout_expansion
regime_module: regime_v1_default
risk_model: risk_governor_v1_default
fusion_module: fusion_geometric_v1
execution_template: execution_manager_v1_default
stop_target_template: none
experiment_type: replay_full_history

# Optional narrative for logs
notes: Operator upload test — three signals only.
```

## What this is **not**

- Not arbitrary natural language strategy descriptions (no silent LLM interpretation).
- Not a way to invent **new catalog signal ids** (e.g. a standalone SAR module) without engineering adding them to `catalog_v1.json` and code first.

## Where uploads go on disk

Under the blackbox repo root (operator-visible in API `disclosure`):

- **Sources:** `runtime/operator_strategy_uploads/sources/`
- **Generated manifests:** `runtime/operator_strategy_uploads/manifests/`
- **Active pointer:** `runtime/operator_strategy_uploads/active.json`

Shipped assets under `renaissance_v4/configs/manifests/` are **never** overwritten by this flow.
