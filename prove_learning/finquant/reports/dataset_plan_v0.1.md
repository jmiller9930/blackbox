# FinQuant-1 Dataset Plan v0.1 — Platinum (crypto-first, indicator-intelligence, statistical rigor)

**To:** Engineering · **Cc:** Operator  
**Re:** Dataset architecture & sourcing plan — **training does not begin** until approved.

**Status:** Plan only · **No training started.**

---

## Mission alignment

FinQuant-1 is a **narrow quant-finance verifier** with **retained general reasoning**. It **does not generate trades**; it **verifies** math, risk, PnL, replay validity, indicator use, and specifies **what DATA must prove**. It must be **crypto-first**, **indicator-intelligent**, and **statistically literate**, and it must **challenge claims** and **require proof**.

---

## Golden Mix (v0.1)

**Total initial corpus:** **10,000–20,000** high-quality supervised samples (JSONL). Nominal target used for planning: **15,000**.

| Golden pillar | Share | @ 10k | @ 15k (nominal) | @ 20k |
|---------------|-------|-------|-------------------|-------|
| **Quant / statistical reasoning** | 30% | 3,000 | 4,500 | 6,000 |
| **Crypto market structure & derivatives** | 30% | 3,000 | 4,500 | 6,000 |
| **Indicator intelligence & interaction** | 25% | 2,500 | 3,750 | 5,000 |
| **Implementation & code review** | 15% | 1,500 | 2,250 | 3,000 |
| **Total** | 100% | 10,000 | 15,000 | 20,000 |

**Cross-cutting constraint:** ≥ **50%** of all samples are **negative**, **trap**, or **adversarial** (wrong math, misuse, leakage, regime mismatch, buggy code, policy drift). The verifier must **catch errors**, not only solve clean textbook items.

---

## Dataset categories (all required)

The thirteen pillars below are **content themes**. Samples map into the **Golden Mix** buckets (some rows span multiple pillars — authoring tags multi-label).

### Allocation target @ **15,000** nominal (exact counts; sums to 15,000)

| # | Category | Target samples (v0.1 @ 15k) | Primary golden bucket(s) |
|---|-----------|------------------------------|---------------------------|
| 1 | Financial Math & PnL Accounting | 1,200 | Quant / stat · Crypto |
| 2 | Crypto Market Structure | 1,400 | Crypto |
| 3 | Indicator Intelligence (core) | 2,400 | Indicator |
| 4 | Statistical / Quant Indicators (SPAR-class) | 2,200 | Quant / stat |
| 5 | Order Flow / Microstructure | 600 | Crypto · Indicator |
| 6 | Derivatives Signals (crypto) | 800 | Crypto |
| 7 | Volatility Structure | 600 | Quant / stat · Indicator |
| 8 | Multi-Timeframe & Interaction | 900 | Indicator · Quant / stat |
| 9 | Backtest / Replay Integrity | 1,200 | Quant / stat · Code |
|10 | Policy-vs-Implementation | 700 | Code · Crypto |
|11 | Python Quant Code Review | 1,800 | Code |
|12 | Financial Tables / Filings (light) | 400 | Quant / stat |
|13 | DATA Validation Prompts | 900 | All (cross-cutting) |

**Note:** Tags overlap (e.g., funding PnL spans 1, 2, 6). Authors maintain **pillar quotas** and **golden-mix quotas** simultaneously via metadata (`golden_bucket`, `categories[]`, `polarity`: positive|negative|adversarial).

---

### 1. Financial Math & PnL Accounting

- Trade lifecycle PnL: fees, funding, slippage; realized vs unrealized.
- Position sizing, leverage, margin, liquidation thresholds.
- Drawdown, expectancy, Sharpe / Sortino (definitions, misuse, annualization caveats).

### 2. Crypto Market Structure

- 24/7 sessions, gap semantics vs equities; volatility clustering.
- Spot vs perp; funding **level + trend**; basis; index vs mark.
- Open interest vs price; liquidation cascades (qualitative + quantitative traps).
- Liquidity fragmentation, spreads, depth, adverse selection.

### 3. Indicator Intelligence (core)

Per indicator: **definition**, **computation**, **assumptions**, **regime dependence**, **failure modes**.  
**Coverage:** RSI, EMA/SMA, MACD, ATR, VWAP, Bollinger Bands, volume profiles, OBV.

**Doctrine:** Indicators are **probabilistic**, **regime-dependent**, **interactive/conflicting**; assumptions **break**. **No** encoded trading rules (e.g., “RSI &lt; 30 ⇒ buy”).

### 4. Statistical / Quant Indicators (SPAR-class)

- z-score & mean-reversion assumptions; stationarity pitfalls.
- Rolling variance/std; realized vol; window sensitivity.
- Correlation instability; breakdown under regime shift.
- Cointegration / pair logic (hypothesis, drift).
- Regime classification (trend/vol/chop); label leakage traps.
- Signal stability and decay.

### 5. Order Flow / Microstructure

- Order book imbalance; delta; aggressor side approximations.
- Liquidity gaps; impact; slippage modeling assumptions.

### 6. Derivatives Signals (crypto)

- Funding rate level + change; interpretation traps.
- OI delta vs price; causality vs correlation.
- Long/short ratios — sampling bias caveats.
- Liquidation clusters; basis compression/expansion.

### 7. Volatility Structure

- Expansion/contraction; squeezes; range compression.
- Vol regime shifts; vol clustering vs mean reversion of vol.

### 8. Multi-Timeframe & Interaction

- Cross-TF conflicts; dominance rules vs narrative traps.
- Momentum vs mean-reversion indicator tension.
- Stacked lag effects; peeking across TFs (leakage).

### 9. Backtest / Replay Integrity

- Lookahead, leakage, timestamp alignment; bar vs trade resolution.
- Fill assumptions; partial fills; queue position fantasy.
- Survivorship, selection bias; implicit filtering.

### 10. Policy-vs-Implementation

- Spec vs code divergence; hidden defaults.
- Parameter drift; undocumented state; rounding inconsistencies.

### 11. Python Quant Code Review

- pandas/numpy correctness; timezone-aware indexing.
- Rolling windows (centered vs trailing), off-by-one, warm-up periods.
- Vectorization pitfalls; deterministic replay hooks.
- Unit-test expectations for PnL/risk modules.

### 12. Financial Tables / Filings (light)

- FinQA-style table QA; map rows to PnL/risk conclusions.
- Light touch only — **no raw SEC dumps** in v0.1 SFT.

### 13. DATA Validation Prompts

- What evidence is required (queries, logs, ledgers, hashes).
- Where to source it (systems of record).
- How to **falsify** the claim; negative controls.

---

## Indicator doctrine (explicit)

| Rule | Statement |
|------|-----------|
| No signal gospel | Do **not** encode fixed buy/sell rules from indicators. |
| Probabilistic | Indicators output **statistics**, not destiny. |
| Regime | Validity is **regime-dependent**; same print means different things in chop vs trend. |
| Interaction | Indicators **interact and conflict**; resolution requires context + DATA. |
| Failure modes | Every indicator example includes **limitations** and **failure modes**. |
| Proof | Strong claims require **DATA path** and **falsifiers**. |

---

## Record format (strict)

Each sample is one JSON object per line (JSONL), fields:

```json
{
  "instruction": "...",
  "input": "...",
  "output": "..."
}
```

Optional metadata (same line object extension — allowed if pipeline supports):

- `categories`, `golden_bucket`, `polarity`, `difficulty`, `source`: synthetic|curated_public|internal_template

---

## Verifier output contract (strict)

Every **`output`** must follow this section structure (headings or labeled blocks):

1. **Claim reviewed**  
2. **Math verdict** (correct / incorrect / insufficient)  
3. **Risk/PnL verdict**  
4. **Indicator validity** (if applicable; else “N/A”)  
5. **Regime considerations**  
6. **Failure modes / edge cases**  
7. **Leakage / overfit concerns**  
8. **Policy-vs-implementation concerns**  
9. **DATA evidence required** (specific queries / logs / fields)  
10. **Final verifier status:** `pass` | `fail` | `needs proof`

---

## Sources (curated)

| Tier | Use in v0.1 |
|------|----------------|
| **Synthetic high-quality** | **Primary** — controlled traps, exact math, crypto/perp nuances. |
| **FinQA-style** | Structured table reasoning (subset). |
| **Curated public excerpts** | Short passages with citation metadata — **no** raw forum dumps. |
| **Internal templates** | PnL/risk/replay/policy patterns — anonymized. |

**Do not** ingest raw SEC dumps or random forums into SFT. Reserve large unstructured corpora for **future RAG**, not v0.1 fine-tuning.

---

## Quality rules

- Step-by-step reasoning where needed; **units explicit** (quote currency, contract size, tick).
- State **assumptions** and **conditions under which conclusions fail**.
- Prefer **precise** over vague; **adversarial** mirrors production mistakes.
- **No** cheerleading “trade ideas”; verifier stance only.

---

## Evaluation plan (held-out)

Build **`eval_v0.1`** (disjoint from train), stratified:

| Eval slice | Examples |
|------------|----------|
| PnL traps | fees, funding sign, leverage, cross-margin assumptions |
| Risk sizing traps | Kelly misunderstandings, vol targeting errors |
| Indicator misuse | regime mismatch, multi-TF peeking |
| Leakage / lookahead | bars, joins, feature timestamps |
| Code bugs | rolling windows, index alignment, warm-up |
| Regime shifts | volatility breaks, correlation breakdown |

**Reported metrics:**

| Metric | Definition |
|--------|------------|
| **Error detection rate** | Fraction of negative/trap items where status ≠ `pass` when appropriate |
| **Math correctness** | Rubric on gold symbolic/numeric checks |
| **False-confidence rate** | `pass` on trap items — **must approach zero** |
| **DATA-requirement coverage** | Presence & specificity of DATA evidence fields (rubric) |

Human + automated graders; deterministic math/code subsets scripted.

---

## Runtime & training technology

| Item | Target |
|------|--------|
| **Base model** | `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` |
| **Adaptation** | **QLoRA** adapter; behavior refocus without erasing general reasoning |
| **Train** | **trx40** RTX A6000 class |
| **Serve** | Export / quantize to **4–5 bit** where possible for **low-cost inference** on lesser hardware |

---

## Scale roadmap

| Phase | Size | Notes |
|-------|------|------|
| **v0.1** | **10k–20k** | Platinum subset; golden mix enforced; ≥50% adversarial |
| **v1.0** | **50k–100k** | Add breadth, harder traps, more code/replay diversity; still curated |
| **RAG** | External | SEC filings, logs corpora — retrieval layer, **not** raw SFT dump |

---

## Example records (≥5 per category — abbreviated)

Below: **five** illustrative triples each; production outputs expand full contract.

### Category 1 — Financial Math & PnL

```json
{"instruction":"Verify perpetual PnL over one funding interval.","input":"Long 10 BTC perp, entry 60,000, exit 60,200, fees 2 bps round-trip, funding paid +0.01% on notional at entry mark.","output":"Claim reviewed: Net trade PnL after fees and funding.\nMath verdict: incorrect if funding omitted.\nRisk/PnL verdict: funding adds cashflow independent of price path.\nIndicator validity: N/A\nRegime considerations: funding sign convention exchange-specific.\nFailure modes: confusing fee base (notional vs filled).\nLeakage/overfit concerns: N/A\nPolicy-vs-implementation concerns: verify fee schedule matches API.\nDATA evidence required: ledger funding payments, fee tier, fill prices.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Trap: user ignores funding in short perp PnL.","input":"Short 5 ETH perp +2% price favorable; claims profit without funding.","output":"Claim reviewed: Short PnL ignoring funding.\nMath verdict: insufficient.\nRisk/PnL verdict: incomplete until funding cashflows applied.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Liquidation distance sanity check.","input":"25x isolate margin, maint 2%, entry 40k, size 1 BTC.","output":"Claim reviewed: Approx liquidation threshold.\nMath verdict: correct only if maintenance formula matches venue.\n...\nDATA evidence required: venue risk engine params.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Sharpe annualization trap.","input":"Daily returns 30 days, Sharpe 3.0 reported annualized ×√365 without stating RF.","output":"Claim reviewed: Sharpe annualization.\nMath verdict: insufficient — risk-free and calendar assumptions unspecified.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Fees on notional vs margin.","input":"Uses margin balance instead of notional for fee calc on perp.","output":"Claim reviewed: Fee base.\nMath verdict: incorrect if venue charges on notional.\n...\nFinal verifier status: fail"}
```

### Category 2 — Crypto Market Structure

```json
{"instruction":"Explain basis spot-perp under funding pressure.","input":"Perp > spot persistently; funding positive large.","output":"Claim reviewed: Basis interpretation.\nMath verdict: insufficient without borrow/latency factors.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Trap: confuses OI up + price up as bullish signal alone.","input":"OI and price both rose; concludes crowded long must unwind soon.","output":"Claim reviewed: OI-price joint movement interpretation.\nIndicator validity: insufficient — requires positioning context.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Liquidation cascade mechanics.","input":"Thin book + clustered stops below.","output":"Claim reviewed: Cascade narrative.\nRisk/PnL verdict: plausible but unverified magnitude.\n...\nDATA evidence required: depth snapshots, liquidation feed.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"24/7 session gap handling vs equities.","input":"Uses overnight gap logic on BTC.","output":"Claim reviewed: Gap analogy.\nMath verdict: incorrect framing — crypto trades continuously.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Fragmentation & price dispersion.","input":"Compares mid across venues without fees/slippage.","output":"Claim reviewed: Cross-venue price equality.\nMath verdict: insufficient.\n...\nFinal verifier status: needs proof"}
```

### Category 3 — Indicator Intelligence

```json
{"instruction":"RSI in strong trend regime.","input":"RSI ‘oversold’ but ADX high trend.","output":"Claim reviewed: RSI oversold implies bounce.\nIndicator validity: incorrect — regime conflict.\nFailure modes: RSI persistence in trends.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"MACD lag vs price spike.","input":"Claims MACD leads spot move on 1m.","output":"Claim reviewed: MACD leading indicator.\nIndicator validity: incorrect — MACD is lagging derived series.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"VWAP anchoring intraday.","input":"Crypto rolls across UTC midnight reset confusion.","output":"Claim reviewed: VWAP session anchor.\nRegime considerations: session boundary matters.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Bollinger squeeze interpretation.","input":"Bandwidth narrow — predicts imminent breakout direction up.","output":"Claim reviewed: Squeeze direction.\nIndicator validity: insufficient — squeeze signals vol compression not direction.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"OBV vs volume spikes spoofing.","input":"OBV rising — assumes accumulation.","output":"Claim reviewed: OBV accumulation thesis.\nFailure modes: spoofed prints inflate volume.\n...\nDATA evidence required: tape/trade classification.\nFinal verifier status: needs proof"}
```

### Category 4 — Statistical / SPAR

```json
{"instruction":"Rolling vol window sensitivity trap.","input":"Uses 5-bar vol for risk on 1h strategy without checking stability.","output":"Claim reviewed: Vol estimate reliability.\nMath verdict: insufficient.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Correlation breakdown during stress.","input":"Assumes stable BTC-ETH correlation for hedge.","output":"Claim reviewed: Static correlation hedge.\nMath verdict: incorrect in regime shift.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Z-score mean reversion validity.","input":"Prices far below MA — assumes stationary.","output":"Claim reviewed: z-score bounce trade.\nMath verdict: insufficient — stationarity unverified.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Cointegration drift trap.","input":"Pairs spread widened — assumes convergence soon.","output":"Claim reviewed: Spread convergence.\nMath verdict: insufficient — hedge ratio drift.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Regime classifier leakage.","input":"Uses future vol labels in features.","output":"Claim reviewed: Regime labels.\nLeakage/overfit concerns: lookahead in labels.\n...\nFinal verifier status: fail"}
```

### Category 5 — Order Flow / Microstructure

```json
{"instruction":"Book imbalance -> short-term direction claim.","input":"Bid depth >> ask depth — predicts next tick up.","output":"Claim reviewed: Imbalance predictive power.\nMath verdict: insufficient — microstructure noise dominates.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Delta vs signed volume approximation trap.","input":"Constructs delta from OHLC only.","output":"Claim reviewed: Delta series.\nMath verdict: incorrect — insufficient data.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Slippage model linear impact forever.","input":"Uses linear market impact for whale size.","output":"Claim reviewed: Impact linearity.\nMath verdict: incorrect — nonlinear impact typical.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Liquidity gap after halt listing.","input":"Ignores auction mechanics on listing day.","output":"Claim reviewed: Liquidity continuity.\nRegime considerations: halt/auction regime.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Spread widening interpretation.","input":"Wide spread implies manipulation only.","output":"Claim reviewed: Spread cause.\nFailure modes: ignores volatility & inventory risk.\n...\nFinal verifier status: needs proof"}
```

### Category 6 — Derivatives Signals

```json
{"instruction":"Funding trend vs single print.","input":"Uses one 8h funding print as sentiment.","output":"Claim reviewed: Funding interpretation.\nIndicator validity: insufficient — need distribution & trend.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Funding vs spot lead-lag myth.","input":"Claims funding causes next-hour spot move deterministically.","output":"Claim reviewed: Causality.\nMath verdict: insufficient — confounded.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"OI delta vs price correlation trap.","input":"Positive correlation implies causality.","output":"Claim reviewed: OI-price causality.\nMath verdict: incorrect inference.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Long/short ratio sample bias.","input":"Uses exchange-only retail ratio as market truth.","output":"Claim reviewed: Positioning representativeness.\n...\nDATA evidence required: comprehensive positioning sources.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Basis convergence trade timing.","input":"Perp rich vs spot; enters convergence trade ignoring borrow/carry.","output":"Claim reviewed: Basis mean reversion timing.\nRisk/PnL verdict: insufficient without carry costs.\n...\nFinal verifier status: needs proof"}
```

### Category 7 — Volatility Structure

```json
{"instruction":"Vol expansion after squeeze — direction claim.","input":"BB squeeze then breakout assumed long.","output":"Claim reviewed: Post-squeeze direction.\nIndicator validity: insufficient — breakout direction not implied.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Low vol forever assumption.","input":"Sells vol without tail narrative.","output":"Claim reviewed: Short vol safety.\nRisk/PnL verdict: incorrect — tail risk ignored.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Regime shift detection without structural break test.","input":"Eyeballs chart for regime change.","output":"Claim reviewed: Regime shift.\nMath verdict: insufficient.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Clustering vs mean reversion confusion.","input":"Interprets vol clustering as fast mean reversion always.","output":"Claim reviewed: Vol dynamics.\nMath verdict: incorrect framing.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Range compression breakout sizing.","input":"Doubles size because compress — ignores liquidity.","output":"Claim reviewed: Position sizing vs compression.\nRisk/PnL verdict: insufficient.\n...\nFinal verifier status: needs proof"}
```

### Category 8 — Multi-Timeframe

```json
{"instruction":"Higher TF trend vs lower TF signal conflict.","input":"1h buy while 1d bearish — ignores dominance.","output":"Claim reviewed: TF conflict resolution.\nIndicator validity: insufficient narrative.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Peek higher TF future leak in features.","input":"Uses closed daily bar before hour closes for intraday label.","output":"Claim reviewed: TF alignment.\nLeakage/overfit concerns: lookahead across TF.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Stacked EMAs multi-TF alignment trap.","input":"Claims edge when 3 TFs align — no OOS evidence.","output":"Claim reviewed: Multi-TF alignment edge.\nOverfit concerns: high.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Momentum vs mean-reversion conflict same chart.","input":"Uses RSI MR and MACD momentum without priority rule.","output":"Claim reviewed: Indicator conflict.\nIndicator validity: inconsistent framework.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Dominance timeframe selection bias.","input":"Chooses TF after seeing results.","output":"Claim reviewed: TF selection.\nLeakage/overfit concerns: researcher degrees of freedom.\n...\nFinal verifier status: fail"}
```

### Category 9 — Backtest / Replay

```json
{"instruction":"Lookahead in feature join on trades table.","input":"Joins features including future bars by mistake.","output":"Claim reviewed: Feature timing.\nLeakage/overfit concerns: lookahead.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Timestamp timezone mismatch replay.","input":"Mixes UTC exchange ts with local CSV.","output":"Claim reviewed: Timestamp alignment.\nMath verdict: incorrect replay.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Survivorship in universe selection.","input":"Backtest only listed perpetuals that survived.","output":"Claim reviewed: Universe bias.\nLeakage/overfit concerns: survivorship.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Fill assumptions optimistic queue position.","input":"Assumes mid fill on market orders during squeeze.","output":"Claim reviewed: Fill model.\nRisk/PnL verdict: unrealistic.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Deterministic replay hash mismatch.","input":"Same strategy different results across runs — ignored nondeterminism in GPU reductions.","output":"Claim reviewed: Replay determinism.\nPolicy-vs-implementation concerns: nondeterministic kernels.\n...\nFinal verifier status: needs proof"}
```

### Category 10 — Policy-vs-Implementation

```json
{"instruction":"Spec says round-down fees; code rounds nearest.","input":"Diff in fee rounding vs policy PDF.","output":"Claim reviewed: Fee rounding.\nPolicy-vs-implementation concerns: mismatch.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Hidden leverage cap in code not in operator docs.","input":"Strategy assumes 10x allowed — code caps 5x.","output":"Claim reviewed: Leverage policy.\nPolicy-vs-implementation concerns: divergence.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Risk limit checks bypassed in fast path.","input":"Emergency cancel bypass skips margin check.","output":"Claim reviewed: Risk enforcement completeness.\n...\nDATA evidence required: code path coverage logs.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Parameter drift undocumented between releases.","input":"Kelly fraction changed silently.","output":"Claim reviewed: Parameter drift.\nPolicy-vs-implementation concerns: undocumented.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Rounding mode inconsistent PnL ledger vs UI.","input":"UI PnL differs from ledger cents.","output":"Claim reviewed: Display vs ledger.\nMath verdict: inconsistent until unified rounding policy.\n...\nFinal verifier status: needs proof"}
```

### Category 11 — Python Quant Code

```json
{"instruction":"Rolling window off-by-one pandas.","input":"Code uses rolling(14).mean() without shift for signal timing.","output":"Claim reviewed: Signal timing vs labels.\nLeakage/overfit concerns: subtle lookahead.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Resample OHLC misalignment.","input":"Resamples 1m to 1h without proper aggregation rules.","output":"Claim reviewed: OHLC aggregation.\nMath verdict: incorrect implementation.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Vectorized vs loop mismatch funding schedule.","input":"Vectorized funding apply ignores funding timestamps crossing hours.","output":"Claim reviewed: Funding application correctness.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"numpy float accumulation error large ledger.","input":"Sums millions of floats naive order.","output":"Claim reviewed: Numeric stability.\nMath verdict: risk of drift — use Decimal where policy requires.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Missing unit tests for fee bracket boundaries.","input":"Fee tier boundary bug at exactly $X volume.","output":"Claim reviewed: Test coverage.\nPolicy-vs-implementation concerns: boundaries.\n...\nFinal verifier status: needs proof"}
```

### Category 12 — Tables / Filings (light)

```json
{"instruction":"FinQA-style: reconcile revenue line items to net change.","input":"Small excerpt table JSON.","output":"Claim reviewed: Table reconciliation.\n...\nDATA evidence required: source filing cells.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Trap: ignores stock-based comp row.","input":"Derives cash flow wrong.","output":"Claim reviewed: SBC handling.\nMath verdict: incorrect.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Margin table vs leverage disclosure mismatch.","input":"Two tables disagree — user picks favorable.","output":"Claim reviewed: Consistency across tables.\n...\nFinal verifier status: needs proof"}
```

```json
{"instruction":"FX translation row misuse.","input":"Uses local currency column as USD.","output":"Claim reviewed: Currency units.\nMath verdict: incorrect.\n...\nFinal verifier status: fail"}
```

```json
{"instruction":"Footnote dependency ignored.","input":"Omits contingent liability note affecting fair value.","output":"Claim reviewed: Completeness.\n...\nFinal verifier status: needs proof"}
```

### Category 13 — DATA Validation

```json
{"instruction":"What logs prove no lookahead in join?","input":"Strategy claims clean join.","output":"Claim reviewed: Lookahead absence.\nDATA evidence required: SQL plans, as-of join keys, row timestamps hashed.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Prove funding applied correctly per interval.","input":"PnL reconciliation dispute.","output":"Claim reviewed: Funding reconciliation.\nDATA evidence required: funding ledger entries matched to positions.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Falsify edge Sharpe claim.","input":"Vendor claims Sharpe 4.","output":"Claim reviewed: Vendor Sharpe.\nDATA evidence required: raw returns series, benchmark RF, exact formula.\nFinal verifier status: needs proof"}
```

```json
{"instruction":"Exchange API proof for fills vs chart prices.","input":"Backtest uses chart mid not fills.","output":"Claim reviewed: Price basis.\nDATA evidence required: execution IDs, slippage vs mid.\nFinal verifier status: fail"}
```

```json
{"instruction":"Verify deterministic replay hash equality across machines.","input":"Replay drift suspicion.","output":"Claim reviewed: Determinism.\nDATA evidence required: docker image digest, seed logs, BLAS settings.\nFinal verifier status: needs proof"}
```

---

## Ready for dataset build?

**Yes — plan is ready for dataset authoring tooling and labeling workflows**, subject to stakeholder sign-off on:

- nominal **15k** vs **10k/20k** bound selection,
- adversarial **≥50%** enforcement in QA,
- evaluation harness priorities.

**Training remains blocked** until explicit approval after dataset QA gates.

---

## Revision

| Version | Date | Notes |
|---------|------|-------|
| v0.1 | 2026-04-28 | Initial platinum dataset architecture plan |
