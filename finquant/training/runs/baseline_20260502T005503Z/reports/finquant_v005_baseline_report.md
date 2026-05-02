# FinQuant v0.05 — Baseline Report

- **Run timestamp:** 2026-05-02T00:55:03Z → 2026-05-02T01:42:32Z
- **Host:** trx40
- **Repo path:** /home/vanayr/blackbox
- **DB path:** /home/vanayr/blackbox/data/sqlite/market_data.db
- **Table:** market_bars_5m
- **Symbol:** SOL-PERP
- **5m row count:** 7244
- **First/last 5m:** 2026-04-03T00:30:00Z → 2026-05-02T00:30:00Z
- **15m bars after resample:** 2413
- **Model endpoint:** http://172.20.2.230:11434
- **Model name:** deepseek-r1:14b
- **Cases:** 100 (smoke=False)

## Category Distribution (truth, hidden from model)

| Category | Count |
|---|---|
| clean_long_continuation | 7 |
| clean_short_continuation | 8 |
| range_chop | 13 |
| false_breakout | 9 |
| failed_breakdown | 4 |
| high_volatility_trap | 13 |
| low_volatility_dead_zone | 0 |
| conflicting_indicators | 0 |
| good_trade_that_loses | 17 |
| bad_trade_that_wins | 11 |
| missed_opportunity | 18 |

## Metrics

- schema_valid_rate: **0.070**
- future_leakage_count: **3**
- risk_reasoning_rate: **1.000**
- no_trade_quality_rate: **0.790**
- learning_record_valid_rate: **0.520**  *(primary gate)*
- decision_distribution: {'ENTER': 0, 'NO_TRADE': 100, 'OTHER': 0}

_Consistency / determinism scoring intentionally OUT OF SCOPE (revised directive 2026-05-01)._ 

## Failure Buckets

| Bucket | Count |
|---|---|
| missing_risk_plan | 93 |
| invalid_learning_record | 48 |
| bad_enum | 5 |
| future_leakage_language | 3 |

## Readiness Classification

**BASELINE_BLOCKED_BY_SCHEMA_OR_LEARNING_RECORDS**

## Hard-Rule Confirmations

- NO_TRAINING_PERFORMED=true
- READ_ONLY_DB_ACCESS=true
- WROTE_ONLY_UNDER_RUN_DIR=true

**FINQUANT_V005_BASELINE_MEASURED_NO_TRAINING_PERFORMED**
