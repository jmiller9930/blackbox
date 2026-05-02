# FinQuant-1 Dataset Build Report v0.1

**Generated:** 2026-04-28T18:58:52Z UTC

**Scope:** Synthetic v0.1 JSONL from approved `dataset_plan_v0.1.md`. **Training not started.**

## Summary

| Metric | Value |
|--------|-------|
| **Total samples** | **6000** |
| **Adversarial / trap fraction** | **52.02%** (target ≥50%) |
| **Verifier headings present** | **100%** (all 10 required lines per record) |
| **Generator** | `finquant/scripts/build_finquant_v01_dataset.py` |
| **Seed** | `42` |
| **SHA256 prefix (file)** | `f5dae851c0f533b2` |

## Category distribution (matches plan @15k × 0.4 → 6k)

| Cat | Planned @6k | Actual |
|-----|---------------|--------|
| 1 | 480 | 480 |
| 2 | 560 | 560 |
| 3 | 960 | 960 |
| 4 | 880 | 880 |
| 5 | 240 | 240 |
| 6 | 320 | 320 |
| 7 | 240 | 240 |
| 8 | 360 | 360 |
| 9 | 480 | 480 |
| 10 | 280 | 280 |
| 11 | 680 | 680 |
| 12 | 160 | 160 |
| 13 | 360 | 360 |

## Golden-bucket tags (heuristic `meta.golden_bucket`)

| Bucket | Count | Note |
|--------|-------|------|
| quant_stat | 2360 | SPAR/PnL/replay/table/DATA prompts |
| crypto_derivatives | 1120 | Structure, microstructure, derivatives |
| indicator | 1560 | RSI/MACD/Bollinger/ATR/VWAP family |
| code_review | 960 | Policy vs code, pandas/numpy |

**Note:** Strict **30/30/25/15** golden-mix enforcement at **training** time may use **weighted sampling** over `meta.golden_bucket`; category quotas follow `dataset_plan_v0.1.md`.

## Quality enforcement (Phase 2)

- Every `output` includes explicit **Math / Risk-PnL / Indicator / Regime / Failure modes / Leakage / Policy / DATA / Status**.
- Adversarial rows emphasize **incorrect math, misuse, leakage, regime mismatch, bad code**.
- Records carry `meta.polarity` and `meta.category_id` for QA (strip `meta` before SFT if trainer requires strict triple-only).

## Phase 4 — Spot evaluation (manual)

| Teaching objective | Assessment |
|--------------|------------|
| Challenge assumptions | **Yes** — adversarial prompts force rejection or `needs proof`. |
| Detect errors | **Yes** — math/code/leakage traps with `fail` / `needs proof`. |
| Require DATA validation | **Yes** — `DATA evidence required` block on every row. |
| Avoid false confidence | **Designed for** — statuses avoid unconditional `pass` on traps. |

## Known weak areas / follow-ups

- **Synthetic templates:** diversify phrasing and numeric regimes in v0.2 (more paraphrase, venue-specific fee schedules).
- **Golden mix:** optional rebalance script to hit exact 30/30/25/15 if required before training.
- **Human spot-review:** sample 200 rows for tone and crypto-realism.
- **Hard negatives:** add exchange-specific liquidation formulas from public docs (curated).

## Readiness

**Ready for dataset QA sign-off and training pipeline wiring — training execution remains blocked until operator approval.**

## Sample records (3 per category, truncated `output`)

### Category 1

#### Sample 1

```json
{
  "instruction": "[v01-c1-s140] Verify reported net PnL on AVAX-PERP long when funding cashflows are omitted and fees are applied to margin not notional.",
  "input": "Position 37 AVAX; entry 68346, exit +75 USD notional move; claimed profit uses mid marks only; per-side fee 6 bps on notional; positive funding ignored.",
  "output": "Claim reviewed: Net trade economics on AVAX-PERP ignoring funding and possibly mis-stating fee base.\nMath verdict: incorrect / insufficient until funding and fee basis match venue policy.\nRisk/PnL verdict: Risk controls based on false PnL may mis-size exposure.\nIndicator validity: N/A\nRegime considerations: Perpetual funding regime applies every interval—cannot assume equity spot logic.\nFailure modes / edge cases: Confusing fee base (notional vs margin); omitting funding; using chart mid vs fills.\nLeakage / overfit concerns: N/A unless labels used future marks.\nPolicy-vs-implementation concerns: Cross-check fee tier JSON vs matching engine rounding mode.\nDATA evidence required: Funding ledger rows for position id; fee invoices; actual fills vs mid reconstruction.\nFinal verifier status: fail",
  "meta": {
    "category_id": 1,
    "golden_bucket": "quant_stat",
    "polarity": "adversarial",
    "tag": "v01-c1-s140"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c1-s309] Reconcile spot-equivalent PnL including fees for a fully specified perp round-trip.",
  "input": "AVAX-PERP long 2 contracts; entry mark 62_000; exit 62_400; round-trip fee 8 bps notional each side; funding paid −0.005% on entry notional once. Provide net USD.",
  "output": "Claim reviewed: Fully specified fee+funding perp PnL.\nMath verdict: correct once formulas applied with venue definitions (verify rounding).\nRisk/PnL verdict: Sizing sound only if liquidation buffer unchanged.\nIndicator validity: N/A\nRegime considerations: High leverage raises liquidation proximity—monitor margin asset volatility.\nFailure modes / edge cases: Rounding at settlement boundaries; partial fills vs assumptions.\nLeakage / overfit concerns: N/A for this toy ledger.\nPolicy-vs-implementation concerns: Ensure fee schedule matches VIP tier used.\nDATA evidence required: Signed fills CSV + funding rows + fee tier snapshot.\nFinal verifier status: pass",
  "meta": {
    "category_id": 1,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c1-s309"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c1-s276] Verify reported net PnL on AVAX-PERP long when funding cashflows are omitted and fees are applied to margin not notional.",
  "input": "Position 5 AVAX; entry 63463, exit +284 USD notional move; claimed profit uses mid marks only; per-side fee 4 bps on notional; positive funding ignored.",
  "output": "Claim reviewed: Net trade economics on AVAX-PERP ignoring funding and possibly mis-stating fee base.\nMath verdict: incorrect / insufficient until funding and fee basis match venue policy.\nRisk/PnL verdict: Risk controls based on false PnL may mis-size exposure.\nIndicator validity: N/A\nRegime considerations: Perpetual funding regime applies every interval—cannot assume equity spot logic.\nFailure modes / edge cases: Confusing fee base (notional vs margin); omitting funding; using chart mid vs fills.\nLeakage / overfit concerns: N/A unless labels used future marks.\nPolicy-vs-implementation concerns: Cross-check fee tier JSON vs matching engine rounding mode.\nDATA evidence required: Funding ledger rows for position id; fee invoices; actual fills vs mid reconstruction.\nFinal verifier status: fail",
  "meta": {
    "category_id": 1,
    "golden_bucket": "quant_stat",
    "polarity": "adversarial",
    "tag": "v01-c1-s276"
  }
}
```

### Category 2

#### Sample 1

```json
{
  "instruction": "[v01-c2-s246] Explain basis spot-vs-BTC-PERP under persistent positive funding.",
  "input": "Perp trades rich vs index spot for multiple intervals; funding positive and stable.",
  "output": "Claim reviewed: Interpret rich perp vs spot under positive funding.\nMath verdict: directionally coherent but magnitude needs borrow/latency costs.\nRisk/PnL verdict: Carry drag may dominate short scalps.\nIndicator validity: N/A\nRegime considerations: Funding regimes flip—carry traders vs hedgers.\nFailure modes / edge cases: Stale index composition; oracle latency.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Mark/index methodology documented.\nDATA evidence required: Index constituents; oracle timestamps; borrow curves.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 2,
    "golden_bucket": "crypto_derivatives",
    "polarity": "positive",
    "tag": "v01-c2-s246"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c2-s18] Explain basis spot-vs-ETH-PERP under persistent positive funding.",
  "input": "Perp trades rich vs index spot for multiple intervals; funding positive and stable.",
  "output": "Claim reviewed: Interpret rich perp vs spot under positive funding.\nMath verdict: directionally coherent but magnitude needs borrow/latency costs.\nRisk/PnL verdict: Carry drag may dominate short scalps.\nIndicator validity: N/A\nRegime considerations: Funding regimes flip—carry traders vs hedgers.\nFailure modes / edge cases: Stale index composition; oracle latency.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Mark/index methodology documented.\nDATA evidence required: Index constituents; oracle timestamps; borrow curves.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 2,
    "golden_bucket": "crypto_derivatives",
    "polarity": "positive",
    "tag": "v01-c2-s18"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c2-s94] Explain basis spot-vs-BTC-PERP under persistent positive funding.",
  "input": "Perp trades rich vs index spot for multiple intervals; funding positive and stable.",
  "output": "Claim reviewed: Interpret rich perp vs spot under positive funding.\nMath verdict: directionally coherent but magnitude needs borrow/latency costs.\nRisk/PnL verdict: Carry drag may dominate short scalps.\nIndicator validity: N/A\nRegime considerations: Funding regimes flip—carry traders vs hedgers.\nFailure modes / edge cases: Stale index composition; oracle latency.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Mark/index methodology documented.\nDATA evidence required: Index constituents; oracle timestamps; borrow curves.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 2,
    "golden_bucket": "crypto_derivatives",
    "polarity": "positive",
    "tag": "v01-c2-s94"
  }
}
```

### Category 3

#### Sample 1

```json
{
  "instruction": "[v01-c3-s16] Describe what ATR(14) measures and how regime changes interpretation on BTC-PERP.",
  "input": "Provide assumptions and failure modes—not trading instructions.",
  "output": "Claim reviewed: Educational summary of ATR(14) interpretation constraints.\nMath verdict: correct at definitional level—verify parameter window matches feed.\nRisk/PnL verdict: Misapplication risk when volatility shifts abruptly.\nIndicator validity: ATR(14) measures constructed statistic—not destiny.\nRegime considerations: Volatility expansion/contraction changes signal persistence.\nFailure modes / edge cases: Sampling gaps; session resets for VWAP; stale feeds.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Indicator params frozen vs research drift.\nDATA evidence required: Feed spec; parameter JSON; exchange timestamp alignment.\nFinal verifier status: pass",
  "meta": {
    "category_id": 3,
    "golden_bucket": "indicator",
    "polarity": "positive",
    "tag": "v01-c3-s16"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c3-s249] Describe what VWAP(session) measures and how regime changes interpretation on SOL-PERP.",
  "input": "Provide assumptions and failure modes—not trading instructions.",
  "output": "Claim reviewed: Educational summary of VWAP(session) interpretation constraints.\nMath verdict: correct at definitional level—verify parameter window matches feed.\nRisk/PnL verdict: Misapplication risk when volatility shifts abruptly.\nIndicator validity: VWAP(session) measures constructed statistic—not destiny.\nRegime considerations: Volatility expansion/contraction changes signal persistence.\nFailure modes / edge cases: Sampling gaps; session resets for VWAP; stale feeds.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Indicator params frozen vs research drift.\nDATA evidence required: Feed spec; parameter JSON; exchange timestamp alignment.\nFinal verifier status: pass",
  "meta": {
    "category_id": 3,
    "golden_bucket": "indicator",
    "polarity": "positive",
    "tag": "v01-c3-s249"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c3-s9] Trap: treat ATR(14) oversold reading as automatic mean-reversion buy in strong trend.",
  "input": "ADX high trend day on SOL; RSI prints oversold twice; author buys spot assuming bounce.",
  "output": "Claim reviewed: ATR(14) oversold implies bounce suitable for spot entry.\nMath verdict: indicator arithmetic may be fine but inference incorrect.\nRisk/PnL verdict: Trend exhaustion risk underestimated.\nIndicator validity: ATR(14) invalid as standalone MR signal in strong trend—persistent extremes occur.\nRegime considerations: Trend vs chop—indicator semantics shift materially.\nFailure modes / edge cases: Lag; periodic extremes in momentum regimes; volatility crush.\nLeakage / overfit concerns: If labels peek future troughs—invalidate.\nPolicy-vs-implementation concerns: Strategy doc must state MR filters vs trend filters.\nDATA evidence required: ADX series; regime labels methodology; trade list.\nFinal verifier status: fail",
  "meta": {
    "category_id": 3,
    "golden_bucket": "indicator",
    "polarity": "adversarial",
    "tag": "v01-c3-s9"
  }
}
```

### Category 4

#### Sample 1

```json
{
  "instruction": "[v01-c4-s812] Assess rolling realized vol window sensitivity for BTC-PERP risk caps.",
  "input": "Compare 10-bar vs 30-bar realized vol on 1h bars—same annualization assumptions.",
  "output": "Claim reviewed: Vol estimate stability across windows.\nMath verdict: correct comparison if annualization formula identical and bars aligned.\nRisk/PnL verdict: Wrong window mis-calibrates VaR bands.\nIndicator validity: Vol estimator choice is statistical assumption-heavy.\nRegime considerations: Vol clustering means short windows noisy.\nFailure modes / edge cases: Microstructure noise at low liquidity; missing bars.\nLeakage / overfit concerns: Centered windows leak if used live.\nPolicy-vs-implementation concerns: Risk engine documents vol estimator.\nDATA evidence required: Bar construction logs; clock sync; missing bar policy.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 4,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c4-s812"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c4-s221] Trap: pair-trade hedge using stable rolling correlation on AVAX/ETH during stress.",
  "input": "Uses 30d rolling corr=0.92 to size hedge; March shock week ignored in rationale.",
  "output": "Claim reviewed: Static correlation suffices for hedge sizing under stress.\nMath verdict: incorrect — correlation unstable; conditional beta shifts.\nRisk/PnL verdict: Severe tail mismatch—basis jump risk.\nIndicator validity: Correlation instability invalidates naive z-score MR assumptions.\nRegime considerations: Stress regime breaks cointegration maintenance.\nFailure modes / edge cases: Regime shift; liquidity disappearance; funding asymmetry.\nLeakage / overfit concerns: If correlation uses future-centered window—fatal.\nPolicy-vs-implementation concerns: Risk limits must enforce stress correlation shocks.\nDATA evidence required: Rolling corr series; EWMA vs Pearson; tail dependence metrics.\nFinal verifier status: fail",
  "meta": {
    "category_id": 4,
    "golden_bucket": "quant_stat",
    "polarity": "adversarial",
    "tag": "v01-c4-s221"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c4-s87] Trap: pair-trade hedge using stable rolling correlation on SOL/ETH during stress.",
  "input": "Uses 30d rolling corr=0.92 to size hedge; March shock week ignored in rationale.",
  "output": "Claim reviewed: Static correlation suffices for hedge sizing under stress.\nMath verdict: incorrect — correlation unstable; conditional beta shifts.\nRisk/PnL verdict: Severe tail mismatch—basis jump risk.\nIndicator validity: Correlation instability invalidates naive z-score MR assumptions.\nRegime considerations: Stress regime breaks cointegration maintenance.\nFailure modes / edge cases: Regime shift; liquidity disappearance; funding asymmetry.\nLeakage / overfit concerns: If correlation uses future-centered window—fatal.\nPolicy-vs-implementation concerns: Risk limits must enforce stress correlation shocks.\nDATA evidence required: Rolling corr series; EWMA vs Pearson; tail dependence metrics.\nFinal verifier status: fail",
  "meta": {
    "category_id": 4,
    "golden_bucket": "quant_stat",
    "polarity": "adversarial",
    "tag": "v01-c4-s87"
  }
}
```

### Category 5

#### Sample 1

```json
{
  "instruction": "[v01-c5-s203] Evaluate linear market impact model limits for large clip on thin AVAX book.",
  "input": "Model: Δprice = λ * signed_volume; λ constant across sizes.",
  "output": "Claim reviewed: Linear impact forever.\nMath verdict: insufficient — convex impact typical.\nRisk/PnL verdict: Underestimates tail cost.\nIndicator validity: N/A\nRegime considerations: Liquidity episodic—λ not stable.\nFailure modes / edge cases: Self-impact loops; latency arbitrage.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Simulator params bounded vs production.\nDATA evidence required: Historical impact curves; depth snapshots.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 5,
    "golden_bucket": "crypto_derivatives",
    "polarity": "positive",
    "tag": "v01-c5-s203"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c5-s114] Evaluate linear market impact model limits for large clip on thin SOL book.",
  "input": "Model: Δprice = λ * signed_volume; λ constant across sizes.",
  "output": "Claim reviewed: Linear impact forever.\nMath verdict: insufficient — convex impact typical.\nRisk/PnL verdict: Underestimates tail cost.\nIndicator validity: N/A\nRegime considerations: Liquidity episodic—λ not stable.\nFailure modes / edge cases: Self-impact loops; latency arbitrage.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Simulator params bounded vs production.\nDATA evidence required: Historical impact curves; depth snapshots.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 5,
    "golden_bucket": "crypto_derivatives",
    "polarity": "positive",
    "tag": "v01-c5-s114"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c5-s215] Evaluate linear market impact model limits for large clip on thin ETH book.",
  "input": "Model: Δprice = λ * signed_volume; λ constant across sizes.",
  "output": "Claim reviewed: Linear impact forever.\nMath verdict: insufficient — convex impact typical.\nRisk/PnL verdict: Underestimates tail cost.\nIndicator validity: N/A\nRegime considerations: Liquidity episodic—λ not stable.\nFailure modes / edge cases: Self-impact loops; latency arbitrage.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Simulator params bounded vs production.\nDATA evidence required: Historical impact curves; depth snapshots.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 5,
    "golden_bucket": "crypto_derivatives",
    "polarity": "positive",
    "tag": "v01-c5-s215"
  }
}
```

### Category 6

#### Sample 1

```json
{
  "instruction": "[v01-c6-s142] Compare funding trend vs single print for SOL-PERP carry reasoning.",
  "input": "Series last 14 intervals stable positive vs one-off spike yesterday.",
  "output": "Claim reviewed: Trend vs spike distinction matters for carry forecasts.\nMath verdict: coherent—quantify trend slope confidence.\nRisk/PnL verdict: Borrow/latency may dominate tiny funding.\nIndicator validity: Treat funding as probabilistic pressure gauge.\nRegime considerations: Trending premium vs mean-reverting premium differs.\nFailure modes / edge cases: Cross-exchange arbitrage breaks local narrative.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Which venue reference for portfolio.\nDATA evidence required: Interval-aligned funding pulls; premium constituents.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 6,
    "golden_bucket": "crypto_derivatives",
    "polarity": "positive",
    "tag": "v01-c6-s142"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c6-s238] Trap: single 8h funding print as definitive sentiment on SOL-PERP.",
  "input": "Funding +0.03% once; concludes longs must pay forever upward.",
  "output": "Claim reviewed: Single funding observation proves sustained carry burden.\nMath verdict: insufficient — distribution unknown.\nRisk/PnL verdict: Trade thesis fragile.\nIndicator validity: Funding rate is noisy funding-pressure statistic—not price oracle.\nRegime considerations: Funding spikes cluster around squeezes.\nFailure modes / edge cases: Oracle glitch; settlement delays; exchange-specific caps.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Funding caps / clamps documented.\nDATA evidence required: Historical funding series; premium index components.\nFinal verifier status: fail",
  "meta": {
    "category_id": 6,
    "golden_bucket": "crypto_derivatives",
    "polarity": "adversarial",
    "tag": "v01-c6-s238"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c6-s193] Compare funding trend vs single print for BTC-PERP carry reasoning.",
  "input": "Series last 14 intervals stable positive vs one-off spike yesterday.",
  "output": "Claim reviewed: Trend vs spike distinction matters for carry forecasts.\nMath verdict: coherent—quantify trend slope confidence.\nRisk/PnL verdict: Borrow/latency may dominate tiny funding.\nIndicator validity: Treat funding as probabilistic pressure gauge.\nRegime considerations: Trending premium vs mean-reverting premium differs.\nFailure modes / edge cases: Cross-exchange arbitrage breaks local narrative.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Which venue reference for portfolio.\nDATA evidence required: Interval-aligned funding pulls; premium constituents.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 6,
    "golden_bucket": "crypto_derivatives",
    "polarity": "positive",
    "tag": "v01-c6-s193"
  }
}
```

### Category 7

#### Sample 1

```json
{
  "instruction": "[v01-c7-s76] Predict breakout direction from Bollinger squeeze alone on AVAX.",
  "input": "Bandwidthmin percentile 5%; author opens long before breakout.",
  "output": "Claim reviewed: Squeeze implies directional breakout bias.\nMath verdict: insufficient — squeeze signals compression not direction.\nRisk/PnL verdict: False breakout both ways.\nIndicator validity: Bollinger squeeze ≠ directional edge absent confirming structure.\nRegime considerations: Mean-reverting chop produces repeated squeezes.\nFailure modes / edge cases: Flash wicks; feed outages widening bands artificially.\nLeakage / overfit concerns: Future volatility labels in training—trap.\nPolicy-vs-implementation concerns: Research sandbox vs prod params frozen.\nDATA evidence required: Band formula; feed quality metrics.\nFinal verifier status: fail",
  "meta": {
    "category_id": 7,
    "golden_bucket": "indicator",
    "polarity": "adversarial",
    "tag": "v01-c7-s76"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c7-s136] Predict breakout direction from Bollinger squeeze alone on SOL.",
  "input": "Bandwidthmin percentile 5%; author opens long before breakout.",
  "output": "Claim reviewed: Squeeze implies directional breakout bias.\nMath verdict: insufficient — squeeze signals compression not direction.\nRisk/PnL verdict: False breakout both ways.\nIndicator validity: Bollinger squeeze ≠ directional edge absent confirming structure.\nRegime considerations: Mean-reverting chop produces repeated squeezes.\nFailure modes / edge cases: Flash wicks; feed outages widening bands artificially.\nLeakage / overfit concerns: Future volatility labels in training—trap.\nPolicy-vs-implementation concerns: Research sandbox vs prod params frozen.\nDATA evidence required: Band formula; feed quality metrics.\nFinal verifier status: fail",
  "meta": {
    "category_id": 7,
    "golden_bucket": "indicator",
    "polarity": "adversarial",
    "tag": "v01-c7-s136"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c7-s231] Predict breakout direction from Bollinger squeeze alone on SOL.",
  "input": "Bandwidthmin percentile 5%; author opens long before breakout.",
  "output": "Claim reviewed: Squeeze implies directional breakout bias.\nMath verdict: insufficient — squeeze signals compression not direction.\nRisk/PnL verdict: False breakout both ways.\nIndicator validity: Bollinger squeeze ≠ directional edge absent confirming structure.\nRegime considerations: Mean-reverting chop produces repeated squeezes.\nFailure modes / edge cases: Flash wicks; feed outages widening bands artificially.\nLeakage / overfit concerns: Future volatility labels in training—trap.\nPolicy-vs-implementation concerns: Research sandbox vs prod params frozen.\nDATA evidence required: Band formula; feed quality metrics.\nFinal verifier status: fail",
  "meta": {
    "category_id": 7,
    "golden_bucket": "indicator",
    "polarity": "adversarial",
    "tag": "v01-c7-s231"
  }
}
```

### Category 8

#### Sample 1

```json
{
  "instruction": "[v01-c8-s318] Multi-TF conflict: 1m MACD buy vs 1d downtrend—pick winner without rules.",
  "input": "Retail bot buys 1m MACD cross while daily structure bearish.",
  "output": "Claim reviewed: Lower TF signal overrides higher TF trend absent governance.\nMath verdict: insufficient — conflict resolution undefined.\nRisk/PnL verdict: Whipsaw amplification.\nIndicator validity: Indicators conflict—priority rules required—not implicit.\nRegime considerations: Higher TF dominance assumption must be explicit.\nFailure modes / edge cases: Repainting lower TF indicators; session boundaries.\nLeakage / overfit concerns: Using closed daily bar before hour closes intraday features.\nPolicy-vs-implementation concerns: Conflict playbook in strategy spec.\nDATA evidence required: Timestamp-aligned bars; higher TF completion proofs.\nFinal verifier status: fail",
  "meta": {
    "category_id": 8,
    "golden_bucket": "indicator",
    "polarity": "adversarial",
    "tag": "v01-c8-s318"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c8-s155] Document stacked lag when RSI(14) on 15m aligns with EMA slope on 4h.",
  "input": "Describe interaction—not a trading rule.",
  "output": "Claim reviewed: Explain lag accumulation across stacked indicators.\nMath verdict: consistent if windows aligned—verify alignment math.\nRisk/PnL verdict: Double-counting momentum exposure.\nIndicator validity: Interaction terms matter—avoid redundant signals.\nRegime considerations: Fast TF noise vs slow TF bias.\nFailure modes / edge cases: Alignment coincidence vs structural coupling.\nLeakage / overfit concerns: Peak future returns used to tune alignment.\nPolicy-vs-implementation concerns: Feature independence tests documented.\nDATA evidence required: Covariance matrix across horizons.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 8,
    "golden_bucket": "indicator",
    "polarity": "positive",
    "tag": "v01-c8-s155"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c8-s301] Multi-TF conflict: 1m MACD buy vs 1d downtrend—pick winner without rules.",
  "input": "Retail bot buys 1m MACD cross while daily structure bearish.",
  "output": "Claim reviewed: Lower TF signal overrides higher TF trend absent governance.\nMath verdict: insufficient — conflict resolution undefined.\nRisk/PnL verdict: Whipsaw amplification.\nIndicator validity: Indicators conflict—priority rules required—not implicit.\nRegime considerations: Higher TF dominance assumption must be explicit.\nFailure modes / edge cases: Repainting lower TF indicators; session boundaries.\nLeakage / overfit concerns: Using closed daily bar before hour closes intraday features.\nPolicy-vs-implementation concerns: Conflict playbook in strategy spec.\nDATA evidence required: Timestamp-aligned bars; higher TF completion proofs.\nFinal verifier status: fail",
  "meta": {
    "category_id": 8,
    "golden_bucket": "indicator",
    "polarity": "adversarial",
    "tag": "v01-c8-s301"
  }
}
```

### Category 9

#### Sample 1

```json
{
  "instruction": "[v01-c9-s323] Survivorship bias risk when universe = listed perps only still trading.",
  "input": "Backtest winners only—delisted contracts omitted.",
  "output": "Claim reviewed: Historical universe matches tradable reality.\nMath verdict: insufficient — survivorship biases returns upward.\nRisk/PnL verdict: Capital deployment assumptions false.\nIndicator validity: N/A\nRegime considerations: Listing churn regime crypto-high.\nFailure modes / edge cases: Manual removals; contract migrations.\nLeakage / overfit concerns: Drop labels informed by future delisting.\nPolicy-vs-implementation concerns: Universe freeze timestamps.\nDATA evidence required: Contract lifecycle table; inclusion criteria.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 9,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c9-s323"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c9-s435] Survivorship bias risk when universe = listed perps only still trading.",
  "input": "Backtest winners only—delisted contracts omitted.",
  "output": "Claim reviewed: Historical universe matches tradable reality.\nMath verdict: insufficient — survivorship biases returns upward.\nRisk/PnL verdict: Capital deployment assumptions false.\nIndicator validity: N/A\nRegime considerations: Listing churn regime crypto-high.\nFailure modes / edge cases: Manual removals; contract migrations.\nLeakage / overfit concerns: Drop labels informed by future delisting.\nPolicy-vs-implementation concerns: Universe freeze timestamps.\nDATA evidence required: Contract lifecycle table; inclusion criteria.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 9,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c9-s435"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c9-s142] Survivorship bias risk when universe = listed perps only still trading.",
  "input": "Backtest winners only—delisted contracts omitted.",
  "output": "Claim reviewed: Historical universe matches tradable reality.\nMath verdict: insufficient — survivorship biases returns upward.\nRisk/PnL verdict: Capital deployment assumptions false.\nIndicator validity: N/A\nRegime considerations: Listing churn regime crypto-high.\nFailure modes / edge cases: Manual removals; contract migrations.\nLeakage / overfit concerns: Drop labels informed by future delisting.\nPolicy-vs-implementation concerns: Universe freeze timestamps.\nDATA evidence required: Contract lifecycle table; inclusion criteria.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 9,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c9-s142"
  }
}
```

### Category 10

#### Sample 1

```json
{
  "instruction": "[v01-c10-s170] Verify hidden leverage cap in risk engine matches operator handbook.",
  "input": "Handbook 10x max; code constant MAX_LEV=5 for retail tier flag True.",
  "output": "Claim reviewed: Effective leverage bound consistent.\nMath verdict: needs_proof until tier routing confirmed.\nRisk/PnL verdict: Users may assume 10x.\nIndicator validity: N/A\nRegime considerations: Retail vs pro tiers.\nFailure modes / edge cases: Flag mis-set during deploy.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Release notes + config hash pinned.\nDATA evidence required: Config artifact + ABAC tier assignments.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 10,
    "golden_bucket": "code_review",
    "polarity": "positive",
    "tag": "v01-c10-s170"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c10-s60] Policy PDF rounds fees down; production code rounds nearest cent asymmetrically.",
  "input": "Mismatch causes systematic sub-cent drift vs treasury ledger.",
  "output": "Claim reviewed: Fee rounding consistent with policy.\nMath verdict: incorrect — divergence detected.\nRisk/PnL verdict: Compliance & treasury reconciliation breaks.\nIndicator validity: N/A\nRegime considerations: High-volume amplifies drift.\nFailure modes / edge cases: Bankers rounding vs truncate; currency conversions.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Patch code or policy—single source of truth.\nDATA evidence required: Diff ledger vs policy simulator on shadow traffic.\nFinal verifier status: fail",
  "meta": {
    "category_id": 10,
    "golden_bucket": "code_review",
    "polarity": "adversarial",
    "tag": "v01-c10-s60"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c10-s260] Policy PDF rounds fees down; production code rounds nearest cent asymmetrically.",
  "input": "Mismatch causes systematic sub-cent drift vs treasury ledger.",
  "output": "Claim reviewed: Fee rounding consistent with policy.\nMath verdict: incorrect — divergence detected.\nRisk/PnL verdict: Compliance & treasury reconciliation breaks.\nIndicator validity: N/A\nRegime considerations: High-volume amplifies drift.\nFailure modes / edge cases: Bankers rounding vs truncate; currency conversions.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Patch code or policy—single source of truth.\nDATA evidence required: Diff ledger vs policy simulator on shadow traffic.\nFinal verifier status: fail",
  "meta": {
    "category_id": 10,
    "golden_bucket": "code_review",
    "polarity": "adversarial",
    "tag": "v01-c10-s260"
  }
}
```

### Category 11

#### Sample 1

```json
{
  "instruction": "[v01-c11-s591] Code review: pandas rolling mean signal uses center=True unintentionally on AVAX returns.",
  "input": "rolling(14).mean() default center=False OK—but author set center=True without noticing lookahead.",
  "output": "Claim reviewed: Rolling features computed without lookahead.\nMath verdict: incorrect — centered rolling leaks future inside window.\nRisk/PnL verdict: Backtest inflated.\nIndicator validity: N/A\nRegime considerations: Any bar frequency.\nFailure modes / edge cases: Off-by-one warm-up; tz-aware index bugs.\nLeakage / overfit concerns: Critical — centered window.\nPolicy-vs-implementation concerns: Lint rule forbidding center=True in signal gen.\nDATA evidence required: Git blame + unit tests boundary rows.\nFinal verifier status: fail",
  "meta": {
    "category_id": 11,
    "golden_bucket": "code_review",
    "polarity": "adversarial",
    "tag": "v01-c11-s591"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c11-s304] Code review: pandas rolling mean signal uses center=True unintentionally on ETH returns.",
  "input": "rolling(14).mean() default center=False OK—but author set center=True without noticing lookahead.",
  "output": "Claim reviewed: Rolling features computed without lookahead.\nMath verdict: incorrect — centered rolling leaks future inside window.\nRisk/PnL verdict: Backtest inflated.\nIndicator validity: N/A\nRegime considerations: Any bar frequency.\nFailure modes / edge cases: Off-by-one warm-up; tz-aware index bugs.\nLeakage / overfit concerns: Critical — centered window.\nPolicy-vs-implementation concerns: Lint rule forbidding center=True in signal gen.\nDATA evidence required: Git blame + unit tests boundary rows.\nFinal verifier status: fail",
  "meta": {
    "category_id": 11,
    "golden_bucket": "code_review",
    "polarity": "adversarial",
    "tag": "v01-c11-s304"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c11-s543] Review numpy float accumulation in large ledger summation.",
  "input": "Sums 10M np.float32 rows for equity — drift vs Decimal policy.",
  "output": "Claim reviewed: Float accumulation acceptable for treasury-grade totals.\nMath verdict: insufficient — may violate tolerance policy.\nRisk/PnL verdict: Silent drift vs auditors.\nIndicator validity: N/A\nRegime considerations: Large N amplifies error.\nFailure modes / edge cases: Kahan summation absent.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Decimal mandated above threshold.\nDATA evidence required: Parallel sum hashes vs Decimal slow path.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 11,
    "golden_bucket": "code_review",
    "polarity": "positive",
    "tag": "v01-c11-s543"
  }
}
```

### Category 12

#### Sample 1

```json
{
  "instruction": "[v01-c12-s60] Map table rows to net change assertion with explicit units.",
  "input": "Two-line excerpt gross vs discounts provided — compute net.",
  "output": "Claim reviewed: Net from explicit rows.\nMath verdict: correct if units homogeneous.\nRisk/PnL verdict: ImmMaterial omissions.\nIndicator validity: N/A\nRegime considerations: Seasonality commentary out of scope.\nFailure modes / edge cases: Thousands vs millions scaling.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Unit encoding metadata.\nDATA evidence required: Source filing cell coordinates.\nFinal verifier status: pass",
  "meta": {
    "category_id": 12,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c12-s60"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c12-s101] Light table QA: revenue walk ignores contra-revenue line in excerpt.",
  "input": "Mini income statement snippet JSON — user nets revenue without contra adjustments.",
  "output": "Claim reviewed: Net revenue calculation from partial table.\nMath verdict: incorrect / incomplete — contra revenue omitted.\nRisk/PnL verdict: Margin ratios mis-stated.\nIndicator validity: N/A\nRegime considerations: GAAP vs non-GAAP mix.\nFailure modes / edge cases: FX translation row confusion.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Mapping table line IDs.\nDATA evidence required: Full filing segment + footnotes cross-ref.\nFinal verifier status: fail",
  "meta": {
    "category_id": 12,
    "golden_bucket": "quant_stat",
    "polarity": "adversarial",
    "tag": "v01-c12-s101"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c12-s31] Light table QA: revenue walk ignores contra-revenue line in excerpt.",
  "input": "Mini income statement snippet JSON — user nets revenue without contra adjustments.",
  "output": "Claim reviewed: Net revenue calculation from partial table.\nMath verdict: incorrect / incomplete — contra revenue omitted.\nRisk/PnL verdict: Margin ratios mis-stated.\nIndicator validity: N/A\nRegime considerations: GAAP vs non-GAAP mix.\nFailure modes / edge cases: FX translation row confusion.\nLeakage / overfit concerns: N/A\nPolicy-vs-implementation concerns: Mapping table line IDs.\nDATA evidence required: Full filing segment + footnotes cross-ref.\nFinal verifier status: fail",
  "meta": {
    "category_id": 12,
    "golden_bucket": "quant_stat",
    "polarity": "adversarial",
    "tag": "v01-c12-s31"
  }
}
```

### Category 13

#### Sample 1

```json
{
  "instruction": "[v01-c13-s142] Enumerate DATA queries to prove no lookahead in feature pipeline.",
  "input": "Describe joins & invariant checks—not SQL dumps.",
  "output": "Claim reviewed: Negative lookahead provability plan.\nMath verdict: N/A\nRisk/PnL verdict: Model risk if unproven.\nIndicator validity: N/A\nRegime considerations: Any.\nFailure modes / edge cases: Clock skew.\nLeakage / overfit concerns: Define PASS/FAIL invariant.\nPolicy-vs-implementation concerns: Replay harness ownership.\nDATA evidence required: SQL explain; max(feature_ts)<=trade_ts grouped; hash parity replay.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 13,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c13-s142"
  }
}
```

#### Sample 2

```json
{
  "instruction": "[v01-c13-s139] Enumerate DATA queries to prove no lookahead in feature pipeline.",
  "input": "Describe joins & invariant checks—not SQL dumps.",
  "output": "Claim reviewed: Negative lookahead provability plan.\nMath verdict: N/A\nRisk/PnL verdict: Model risk if unproven.\nIndicator validity: N/A\nRegime considerations: Any.\nFailure modes / edge cases: Clock skew.\nLeakage / overfit concerns: Define PASS/FAIL invariant.\nPolicy-vs-implementation concerns: Replay harness ownership.\nDATA evidence required: SQL explain; max(feature_ts)<=trade_ts grouped; hash parity replay.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 13,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c13-s139"
  }
}
```

#### Sample 3

```json
{
  "instruction": "[v01-c13-s163] Enumerate DATA queries to prove no lookahead in feature pipeline.",
  "input": "Describe joins & invariant checks—not SQL dumps.",
  "output": "Claim reviewed: Negative lookahead provability plan.\nMath verdict: N/A\nRisk/PnL verdict: Model risk if unproven.\nIndicator validity: N/A\nRegime considerations: Any.\nFailure modes / edge cases: Clock skew.\nLeakage / overfit concerns: Define PASS/FAIL invariant.\nPolicy-vs-implementation concerns: Replay harness ownership.\nDATA evidence required: SQL explain; max(feature_ts)<=trade_ts grouped; hash parity replay.\nFinal verifier status: needs proof",
  "meta": {
    "category_id": 13,
    "golden_bucket": "quant_stat",
    "polarity": "positive",
    "tag": "v01-c13-s163"
  }
}
```
