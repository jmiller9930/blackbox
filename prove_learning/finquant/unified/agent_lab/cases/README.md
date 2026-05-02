# Agent Lab — Case Packs

Each file is a self-contained lifecycle case pack.

## Case format

Cases follow `finquant_lifecycle_case_v1` schema (`schemas/finquant_lifecycle_case_v1.schema.json`).

**Key rule:** future candles must be hidden from the decision step. The lifecycle engine reveals them one step at a time.

## Current case packs

| File | Scenario |
|------|---------|
| `lifecycle_basic_v1.json` | Simple lifecycle — one entry or no-trade decision, then outcome |
| `trend_entry_exit_v1.json` | Trend continuation — identify punch-in and punch-out condition |
| `chop_no_trade_v1.json` | Choppy market — correct behavior is stand-down |
| `false_breakout_exit_v1.json` | False breakout — thesis failed, must punch out |

## Adding new cases

1. Follow the schema in `schemas/finquant_lifecycle_case_v1.schema.json`.
2. Each candle step in `steps[]` must include only bars visible at that step.
3. `outcome_candles` are revealed only by the lifecycle engine after all decisions are made.
