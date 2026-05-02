# FINQUANT Train v0.05 — Baseline Certification Harness Spec

**Document status:** Engineering handoff  
**Purpose:** Define the no-training baseline process for measuring the current FinQuant LLM before any additional fine-tuning, DPO, curriculum expansion, or promotion to application core.  
**Primary objective:** Establish the model’s current behavioral readiness using live/canonical SQLite market data and a strict FinQuant decision contract.  
**Hard rule:** This pass must not train, mutate model weights, alter production data, or modify trading state.

---

## 1. Executive Summary

FinQuant v0.05 already has prior crypto best-practice training. The immediate task is not more general crypto training. The task is to measure whether the current model behaves reliably enough inside the FinQuant agentic trade framework.

The baseline harness must answer:

1. Can the model produce valid structured FinQuant decisions?
2. Can it reason from causal market data only?
3. Can it apply risk/invalidation/no-trade discipline?
4. Can it produce valid learning-record candidates?
5. Can it remain consistent across repeated runs?
6. Is it ready for behavior tuning, blocked by schema/learning failures, or ready for candidate-core promotion?

The required final pass line is:

`FINQUANT_V005_BASELINE_MEASURED_NO_TRAINING_PERFORMED`

---

## 2. Known Lab Topology

Authoritative runtime/data host:

`clawbot.a51.corp`  
`172.20.2.161`  
repo: `/home/jmiller/blackbox`

LLM/Ollama host:

`172.20.2.230`

All relevant data stores are SQLite. No Postgres or MySQL is expected for this baseline.

Primary market data source:

`/home/jmiller/blackbox/data/sqlite/market_data.db`

Primary table:

`market_bars_5m`

Known characteristics from the supplied data map:

- canonical 5-minute bars
- symbol lane: `SOL-PERP`
- approximately 7,241 bars
- recent window from April 2026 into May 2026
- derived from live Pyth tape
- suitable for baseline measurement

Long historical source for later training, not this baseline:

`/home/jmiller/blackbox/renaissance_v4/data/renaissance_v4.sqlite3`

Primary historical table:

`market_bars_5m`

Known characteristics:

- SOLUSDT
- approximately 210,240 bars
- about two years of Binance 5-minute history
- suitable for later curriculum expansion, not first baseline

---

## 3. Scope Boundary

### In scope

The baseline harness must:

- read market data in read-only mode
- resample 5-minute candles into 15-minute candles
- generate sealed decision cases
- call the current FinQuant model
- require strict JSON output
- validate schema
- detect obvious future-leakage language
- score risk completeness
- score no-trade discipline
- score learning-record validity
- repeat a subset of cases for consistency
- write JSONL raw outputs
- write JSON and Markdown summary reports

### Out of scope

The baseline harness must not:

- fine-tune the model
- create DPO pairs
- alter model weights
- write to production SQLite databases
- write to execution ledger
- create live trades
- send orders
- mutate policy assignment
- alter dashboard state
- mark FinQuant promoted automatically

---

## 4. Baseline Run Name and Output Layout

Recommended run directory:

`/home/jmiller/blackbox/runtime/finquant_train_v005/baseline_<timestamp>/`

Required subdirectories:

`cases/`  
`raw_outputs/`  
`failures/`  
`reports/`  
`debug/`

Required artifacts:

`cases/baseline_cases.jsonl`  
`raw_outputs/model_outputs.jsonl`  
`failures/failures.jsonl`  
`reports/finquant_v005_baseline_report.json`  
`reports/finquant_v005_baseline_report.md`  
`debug/run_config.json`  
`debug/data_profile.json`  
`debug/consistency_replay.jsonl`

The report must clearly state:

`NO_TRAINING_PERFORMED=true`

---

## 5. Data Loading Requirements

The harness must open SQLite in read-only mode.

Example DSN pattern:

`file:/home/jmiller/blackbox/data/sqlite/market_data.db?mode=ro`

The harness must inspect table columns before querying. Do not assume exact column names without verification.

Expected logical fields:

- candle open timestamp
- open
- high
- low
- close
- volume
- symbol/canonical symbol

Candidate column names may include:

- `candle_open_utc`
- `open_time`
- `timestamp`
- `canonical_symbol`
- `symbol`
- `open`
- `high`
- `low`
- `close`
- `volume_base`
- `volume`

If multiple volume columns exist, prefer `volume_base`; otherwise use `volume`; otherwise set volume to `0.0` and record a warning.

The loader must print:

- database path
- table name
- resolved timestamp column
- resolved OHLCV columns
- row count
- first timestamp
- last timestamp
- selected symbol
- any missing optional columns

Required pass line:

`DATA_LOAD_PASS`

Required fail line:

`DATA_LOAD_FAIL`

---

## 6. 5m to 15m Resampling

The baseline should measure the model on 15-minute decision intervals.

Because current canonical data is 5-minute, the harness must resample internally.

For every 15-minute bucket:

- open = first open
- high = maximum high
- low = minimum low
- close = last close
- volume = sum volume
- timestamp = bucket start timestamp

The harness must reject or warn on incomplete buckets.

Required pass line:

`RESAMPLE_15M_PASS`

Required fail line:

`RESAMPLE_15M_FAIL`

---

## 7. Feature Calculation

The baseline should calculate simple, transparent features only.

Required features:

- EMA 20
- EMA 50
- EMA 200
- RSI 14
- ATR 14
- ATR ratio
- close vs EMA 200
- recent return
- rolling volume ratio when volume is available

The baseline must avoid complex or hidden alpha features. The goal is behavior measurement, not strategy optimization.

Feature values must be included in the case payload so the model does not need to infer them from raw candles alone.

Required pass line:

`FEATURE_BUILD_PASS`

Required fail line:

`FEATURE_BUILD_FAIL`

---

## 8. Case Generation

Each case is a sealed decision moment.

Recommended baseline size:

- default: 100 cases
- minimum smoke test: 10 cases
- maximum initial baseline: 300 cases

Each case must contain:

- `case_id`
- `symbol`
- `timeframe`
- `decision_time`
- `lookback_candles`
- `feature_snapshot`
- `policy_rules`
- `allowed_data_boundary`
- `hidden_future_window_id`

The model must receive only data available at or before `decision_time`.

Default lookback:

- 96 fifteen-minute candles
- equivalent to 24 hours

Default hidden future window:

- 16 fifteen-minute candles
- equivalent to 4 hours

The hidden future must not be included in the model prompt.

Required pass line:

`CASE_GENERATION_PASS`

Required fail line:

`CASE_GENERATION_FAIL`

---

## 9. Case Category Coverage

The first 100-case baseline should attempt balanced coverage across these categories:

- clean long continuation
- clean short continuation
- range chop / no-trade
- false breakout
- failed breakdown
- high volatility trap
- low volatility dead zone
- conflicting indicators
- good trade that loses
- bad trade that wins
- missed opportunity

If the live `market_data.db` window cannot produce all categories, the harness should still run and report category gaps. Lack of category coverage is not a harness failure, but it must be visible in the report.

---

## 10. Prompt Contract

The model prompt must make clear:

- You are FinQuant.
- Use only the supplied pre-reveal market data.
- Do not infer or reference future candles.
- Return strict JSON only.
- No markdown.
- No prose outside JSON.
- If no trade is justified, choose `NO_TRADE`.
- Missing risk logic is a failure.
- Missing invalidation is a failure.
- Learning-record candidate must be structurally valid.

The prompt must include the active policy/risk rules.

Recommended baseline policy rules:

- `NO_TRADE` is always acceptable when evidence is insufficient.
- Trade decisions must include invalidation.
- Trade decisions must include risk plan.
- Long bias requires trend/risk support.
- Short bias requires trend/risk support.
- Avoid overtrading in chop/conflicting conditions.
- Avoid entries in excessive volatility unless explicitly justified.
- The model may not mention future movement except as hypothetical risk planning.

---

## 11. Required Model Output Schema

The model must return one JSON object per case.

Required top-level fields:

`schema_version`  
`case_id`  
`decision`  
`direction`  
`confidence`  
`thesis`  
`competing_hypothesis`  
`invalidation`  
`risk_plan`  
`why_no_trade`  
`expected_failure_mode`  
`learning_record_candidate`

Allowed `decision` values:

`ENTER`  
`NO_TRADE`

Allowed `direction` values:

`LONG`  
`SHORT`  
`NONE`

Confidence:

- numeric
- 0.0 to 1.0

Required `risk_plan` fields:

`stop_logic`  
`target_logic`  
`max_loss_awareness`  
`position_sizing_comment`

Required `learning_record_candidate` fields:

`setup_signature`  
`decision_taken`  
`lesson_if_win`  
`lesson_if_loss`  
`promotion_candidate`  
`do_not_promote_reason`

For `NO_TRADE`, `direction` must be `NONE`, and `why_no_trade` must be non-empty.

For `ENTER`, `direction` must be `LONG` or `SHORT`, and `invalidation` must be non-empty.

---

## 12. LLM Endpoint Requirements

Default endpoint candidate:

`http://172.20.2.230:11434/api/generate`

The model name must be configurable.

Required config fields:

`ollama_base_url`  
`model_name`  
`temperature`  
`top_p`  
`num_predict`  
`request_timeout_seconds`  
`repeat_count_for_consistency`

Recommended baseline settings:

`temperature=0.0`  
`top_p=1.0`  
`num_predict=1200`  
`repeat_count_for_consistency=3`

The harness must print the resolved model name and endpoint before the run starts.

If the model is unreachable, fail with:

`MODEL_ENDPOINT_FAIL`

---

## 13. Validation Scoring

The harness must score every case across these dimensions.

### Schema validity

Pass when:

- output is valid JSON
- required fields exist
- enum values are valid
- confidence is numeric and in range
- nested risk and learning fields exist

Metric:

`schema_valid_rate`

### Causal discipline

Fail if the model uses obvious future-leakage language, including phrases such as:

- “later candles show”
- “as we can see after”
- “future price”
- “the next bars confirm”
- “subsequent move proves”
- “after the decision”

Metric:

`future_leakage_count`

### Risk completeness

Pass when:

- invalidation present for trades
- stop logic present
- target logic present
- max-loss awareness present
- sizing comment present

Metric:

`risk_reasoning_rate`

### No-trade quality

Pass when:

- NO_TRADE includes a specific reason
- reason references uncertainty, chop, conflict, volatility, invalidation weakness, or inadequate edge
- no-trade is not blank or generic

Metric:

`no_trade_quality_rate`

### Learning-record validity

Pass when:

- learning object exists
- setup signature exists
- lessons are non-empty
- promotion flag is boolean
- do-not-promote reason is present when promotion is false

Metric:

`learning_record_valid_rate`

### Consistency

Repeat selected cases multiple times and compare:

- same decision
- same direction
- materially similar confidence band
- same primary reason class

Metric:

`consistency_score`

---

## 14. Outcome Reveal — Baseline Optional

For the first baseline, model behavior can be measured without grading profitability.

However, the harness should optionally calculate hidden-future outcome labels for later reporting:

- target hit first
- stop hit first
- neither
- favorable excursion
- adverse excursion
- no-trade avoided loss
- no-trade missed opportunity

Same-candle ambiguity rule:

If stop and target are both touched inside the same candle, count stop first.

This must not be shown to the model during decision generation.

---

## 15. Report Requirements

The Markdown report must include:

- run timestamp
- host
- repo path
- DB path
- table
- row count
- first/last timestamp
- model endpoint
- model name
- number of cases
- category distribution
- schema valid rate
- future leakage count
- risk reasoning rate
- no-trade quality rate
- learning-record valid rate
- consistency score
- failure buckets
- final readiness classification

Required readiness classifications:

`BASELINE_READY_FOR_BEHAVIOR_TUNING`

Use when the model mostly follows schema and reasoning rules but still needs preference/behavior correction.

`BASELINE_BLOCKED_BY_SCHEMA_OR_LEARNING_RECORDS`

Use when schema validity or learning-record validity is too low.

`BASELINE_NOT_READY_FOR_PROMOTION`

Use when causal discipline, risk reasoning, or consistency is materially unsafe.

`BASELINE_READY_FOR_CANDIDATE_CORE_REVIEW`

Use only if all hard gates pass.

---

## 16. Recommended Thresholds

Initial hard thresholds:

- schema validity: 98% or higher
- future leakage critical failures: 0
- risk reasoning rate: 95% or higher
- no-trade quality rate: 90% or higher
- learning-record valid rate: 95% or higher
- consistency score: 90% or higher

Promotion to candidate-core review requires all hard thresholds.

Anything below these thresholds should trigger behavior tuning, not promotion.

---

## 17. Failure Buckets

Each failed output must be logged into one or more buckets:

`invalid_json`  
`missing_required_field`  
`bad_enum`  
`missing_invalidation`  
`missing_risk_plan`  
`missing_no_trade_reason`  
`future_leakage_language`  
`generic_crypto_chatter`  
`overtrading_bias`  
`invalid_learning_record`  
`low_consistency`  
`model_timeout`  
`endpoint_error`

The failure log must preserve:

- case ID
- prompt hash
- raw model output
- parsed output if available
- failure bucket
- validator message

---

## 18. Safety Requirements

The script must:

- open SQLite in read-only mode
- never write to production DBs
- never call order/execution endpoints
- never alter policy assignment
- never alter application state
- write only under `runtime/finquant_train_v005/`
- print `NO_TRAINING_PERFORMED=true`
- include an explicit dry-run banner

---

## 19. Engineering Run Command

Recommended final command shape:

`python3 tools/finquant/baseline_v005.py --db data/sqlite/market_data.db --table market_bars_5m --ollama-url http://172.20.2.230:11434 --model <MODEL_NAME> --cases 100 --out runtime/finquant_train_v005`

A smoke mode should exist:

`python3 tools/finquant/baseline_v005.py --smoke --cases 10`

The script must print clear phase banners:

`PHASE_01_DATA_LOAD`  
`PHASE_02_RESAMPLE_15M`  
`PHASE_03_FEATURE_BUILD`  
`PHASE_04_CASE_GENERATION`  
`PHASE_05_MODEL_CALLS`  
`PHASE_06_VALIDATION`  
`PHASE_07_CONSISTENCY_REPLAY`  
`PHASE_08_REPORT_WRITE`

---

## 20. Acceptance Criteria

Engineering acceptance requires:

1. Script exists.
2. Script runs smoke mode.
3. Script runs 100-case baseline.
4. DB access is read-only.
5. Raw model outputs are preserved.
6. Failure logs are preserved.
7. JSON report is generated.
8. Markdown report is generated.
9. No training occurs.
10. Final line is printed.

Required final line:

`FINQUANT_V005_BASELINE_MEASURED_NO_TRAINING_PERFORMED`

---

## 21. Deliverable Back to Architect/Operator

Engineering should return:

- git commit hash
- command used
- model name tested
- run directory
- report path
- final readiness classification
- top 5 failure buckets
- explicit confirmation that no training occurred
- explicit confirmation that no production DB writes occurred

---

## 22. Next Step After Baseline

Only after the baseline report exists should the team decide whether to:

- fix schema prompting
- add retry/repair parser
- generate behavior-tuning examples
- create DPO pairs
- run SFT repair
- promote to candidate-core review

No further training should be approved until the baseline state is measured.

---

## 23. Engineering Instruction

Build this as a minimal, inspectable, no-frills harness first.

Do not overbuild UI.

Do not add live trading hooks.

Do not mutate the app.

Do not train.

Measure first.

Return proof.

