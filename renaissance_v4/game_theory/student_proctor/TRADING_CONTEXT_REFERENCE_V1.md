# Trading context reference (v1) — codebase map + indicator lexicon + research alignment

**Purpose:** Single **reference** for what “context” means in product JSON (your example shape), **every** indicator kind the repo admits in policy vocabulary (whether a given deployment uses it or not), and where it is implemented. Use this when filling `price_context`, `structure_context`, `pattern_context`, `indicator_context`, `time_context`, and `memory_context`.

**Wiring:** Rich buckets here are **target** semantics. **As-built Student pre-reveal path** = causal **`bars_inclusive_up_to_t`** + optional **`retrieved_student_experience_v1`** only — see `ARCHITECTURE_BACKWARD_LADDER_STUDENT_TABLE.md` **§C.1**. **Memory = approximation in principle**; **exact-key** retrieval v1 vs **tolerance** engine memory — see **§C.2** in the same file.

**Companion:** `ARCHITECTURE_BACKWARD_LADDER_STUDENT_TABLE.md` (non-negotiables, **§0** **trade** / **learned behavior** definitions, pre-reveal rules, **§C.1 wiring status**).

---

## 1. Canonical envelope (target product shape)

Your structured example maps to **layers** everyone can name:

| Bucket | Role | Causal rule |
|--------|------|-------------|
| `price_context` | Where price is **inside the session/window** vs range; last print | Bars ≤ *t* only |
| `structure_context` | Trend / pullback / volatility **regime** labels | Derived from causal bars + optional indicators |
| `pattern_context` | Candidate playbook patterns + confidences | Model/tags from causal features; **not** this trade’s label |
| `indicator_context` | Compressed indicator **state** (relation to VWAP, momentum bucket, volume stance, vol z-score, **EMA stance**, etc.) | Each series computed only through bar index *t* |
| `time_context` | Session clock segment | Wall-clock + session definition, no outcomes |
| `memory_context` | Retrieval count + **prior-revealed** summaries / bias | Must not inject **current** `pnl` / outcome |

**Today’s minimal Student packet** (`student_decision_packet_v1`) carries **OHLCV only** plus optional **`retrieved_student_experience_v1`** — see `student_context_builder_v1.py`, `cross_run_retrieval_v1.py`. Optional **versioned** **`student_context_annex_v1`** (field **`student_context_annex_v1`** on the packet) holds **`price_context` / `structure_context` / `indicator_context` / `time_context`** when a builder is ready — validated by **`validate_student_context_annex_v1`** in `contracts_v1.py`. Rich buckets in the table below remain the **target contract** for builders that **freeze** the same causal rules.

---

## 2. Deep codebase map (where context is built today)

| Concern | Location |
|---------|----------|
| **Causal bar packet (Student)** | `renaissance_v4/game_theory/student_proctor/student_context_builder_v1.py` — `bars_inclusive_up_to_t` from `market_bars_5m` |
| **Cross-run memory into packet** | `renaissance_v4/game_theory/student_proctor/cross_run_retrieval_v1.py` — `retrieved_student_experience_v1` |
| **Pre-reveal forbidden keys** | `renaissance_v4/game_theory/student_proctor/contracts_v1.py` — `PRE_REVEAL_FORBIDDEN_KEYS_V1` |
| **Operator seam (post-batch)** | `renaissance_v4/game_theory/student_proctor/student_proctor_operator_runtime_v1.py` — `signature_key` = `student_entry_v1:{symbol}:{entry_time}` |
| **Replay feature vector (EMA, ATR, vol, …)** | `renaissance_v4/core/feature_engine.py` → `FeatureSet` in `renaissance_v4/core/feature_set.py` |
| **Rolling window for features** | `renaissance_v4/core/market_state_builder.py` — `MarketState` from SQLite rows |
| **Engine pattern context → signature** | `renaissance_v4/game_theory/context_signature_memory.py` — `derive_context_signature_v1(pattern_context_v1)` (regime, volatility bucket, structure tag **shares**) |
| **Policy indicator vocabulary (frozen kinds)** | `renaissance_v4/policy_spec/indicators_v1.py` — `INDICATOR_KIND_VOCABULARY` |
| **Deterministic series (TS intake harness)** | `renaissance_v4/policy_intake/indicator_engine.mjs` — `computeOne(kind, …)` aligned with comment in file to Python validation |
| **Fusion signals (replay manifest)** | `renaissance_v4/signals/*.py` — e.g. `trend_continuation`, `pullback_continuation`, `breakout_expansion`, `mean_reversion_fade` (order documented in `renaissance_v4/game_theory/MANIFEST_REPLAY_INTEGRATION.md`) |
| **Anna chart contract (EMA as trend layers)** | `modules/anna_training/market_event_view.py` — `trend_reference_layers` EMA 20/50/200, primary trend EMA50 |

---

## 3. External research alignment (summary)

Industry and textbook framing consistently split “context” into:

1. **Price / structure** — swings, range vs trend, breakouts (price-action view).
2. **Derived indicators** — usually grouped as **trend**, **momentum**, **volatility**, **volume** (e.g. educational sources on technical indicator taxonomy; regime-aware ML work stresses **no look-ahead** and walk-forward validation).

Your buckets **`price_context` + `structure_context` + `indicator_context`** match that stacking; **`memory_context`** is orthogonal (experience from **past** revealed grades). **Regime** strings in replay (`dominant_regime`, `dominant_volatility_bucket` in `context_signature_memory.py`) align with “regime context” language in quantitative finance ML.

---

## 4. `structure_context` ↔ engine `pattern_context_v1` (semantic alignment)

`derive_context_signature_v1` expects `pattern_context_v1` with:

- `dominant_regime`, `dominant_volatility_bucket` (strings)
- `structure_tag_shares`: `range_like`, `trend_like`, `breakout_like`, `vol_compressed`, `vol_expanding`
- Bar counts: `high_conflict_bars`, `aligned_directional_bars`, `countertrend_directional_bars`, `bars_processed`

Product labels like `market_state: trend_up`, `pullback_state: shallow_pullback`, `volatility_regime: expanding` are **consistent** with those tags — implement as **deterministic mappers** from bar windows, not from future outcomes.

---

## 5. Pattern / signal names in-repo (for `pattern_context.candidate_patterns`)

| Signal module | Typical role |
|---------------|--------------|
| `trend_continuation` | With-trend entries |
| `pullback_continuation` | Dip-in-trend |
| `breakout_expansion` | Compression → expansion |
| `mean_reversion_fade` | Fade / reversion |

Also referenced in manifests and tuning: `context_candidate_search.py` (thresholds for `trend_continuation_*`, `breakout_expansion_*`).

---

## 6. Full indicator lexicon — **context for each kind** (policy vocabulary)

Below: **`kind`** = value in `INDICATOR_KIND_VOCABULARY` (`indicators_v1.py`). **Implementation** = `indicator_engine.mjs` + params validated in `indicators_v1.py`. **Typical contextual reading** = how traders use the number **at time *t*** (not a buy signal by itself). **In Student packet today** = only via future `indicator_context` projection — **not** yet first-class on `student_decision_packet_v1`.

| `kind` | What it measures | Typical **context** labels / notes (at *t*) | Params (v1) |
|--------|------------------|---------------------------------------------|-------------|
| **ema** | Exponential average of price | Short vs long EMA cross / slope → `trend_bias`: bull if stack ordered and price > fast; bear if inverse | `period` |
| **sma** | Simple average | Same as EMA, smoother; distance % from price = “stretched” vs mean | `period` |
| **rsi** | Relative strength (0–100) | `momentum_state`: oversold `<30`, overbought `>70`, neutral between (thresholds are policy) | `period` |
| **atr** | Average true range | `volatility_regime` input; stop sizing; **not** direction by itself | `period` |
| **macd** | Fast EMA − slow EMA, signal, histogram | `momentum_state`: histogram sign, line vs signal cross | `fast_period`, `slow_period`, `signal_period` |
| **bollinger_bands** | Mean ± *k*σ | Price at **band** → compression vs extension; squeeze = low vol | `period`, `std_dev` |
| **vwap** | Volume-weighted average price (cumulative typ. in engine) | `vwap_relation`: `above_vwap` / `below_vwap` / `at_vwap` from close vs series at *t* | (none) |
| **supertrend** | ATR-based trend line | `market_state` helper: long vs short regime flip | `period`, `multiplier` |
| **stochastic** | %K, %D | Similar to RSI buckets; `momentum_state` | `k_period`, `d_period` |
| **adx** | Trend strength | `trend_strength`: weak if ADX low, strong if high (direction from +DI/−DI if exposed) | `period` |
| **cci** | Commodity channel index | Extremes = stretched vs mean | `period` |
| **williams_r** |−100…0 momentum | Same class as RSI/stoch | `period` |
| **mfi** | Money flow with volume | Volume-weighted momentum; **volume_context** | `period` |
| **obv** | On-balance volume | Cumulative flow; rising OBV with price → participation confirmation | (none) |
| **parabolic_sar** | Stop-and-reverse dots | Price vs SAR → short-term trend side | `step`, `max_step` |
| **ichimoku** | Tenkan, Kijun, cloud lines | Cloud relation = larger structure | `tenkan`, `kijun`, `senkou_b` |
| **donchian** | N-period high/low channel | Breakout / range containment | `period` |
| **volume_filter** | Volume vs SMA / threshold | `volume_state`: increasing / dry / normal | `mode`, … (see validator) |
| **body_measurement** | Candle body/wick stats | Candle-shape **context** | per `indicators_v1` |
| **fixed_threshold** | Constant series | Test harness / gate anchor | `value` |
| **divergence** | (declarative hook) | Price vs indicator divergence **context** | per policy |
| **threshold_group** | (meta) | Composite gate groups | per policy |

**FeatureSet** (`feature_set.py`) already exposes related **atomic context**: `ema_fast_10`, `ema_slow_20`, `ema_distance`, `ema_slope`, `volatility_20`, `directional_persistence_10`, `atr_proxy_14`, `compression_ratio`, plus candle geometry — useful to mirror into `structure_context` / `indicator_context` builders.

---

## 7. `memory_context` — two stores (do not conflate)

| Store | Module | What it is |
|-------|--------|------------|
| **Student learning** | `student_learning_store_v1.py`, retrieval in `cross_run_retrieval_v1.py` | Prior **`student_output_v1`** slices matched by `student_entry_v1:…` key |
| **Engine context signature memory** | `context_signature_memory.py` | Replay **`pattern_context_v1`** hashes + bundle outcomes — **engine** path, distinct contract from Student store |

Summaries like `prior_outcomes_summary` must be built only from **post-reveal** material and **never** smuggle the **pending** trade’s Referee row into the pre-reveal packet.

---

## 8. What remains “not context” (pre-reveal)

Any string key in `PRE_REVEAL_FORBIDDEN_KEYS_V1`, future bars, or **this** graded unit’s `OutcomeRecord` / PnL / exit — see `DIRECTIVE_02_ACCEPTANCE_SUPPLEMENT.md`.

---

## 9. Revision history

| Version | Date | Notes |
|---------|------|--------|
| 1.0 | 2026-04-20 | Initial: codebase deep map, full `INDICATOR_KIND_VOCABULARY` context table, pattern/signal names, research alignment, memory split. |
| 1.1 | 2026-04-20 | Purpose: pointer to **§C.1** (target vs as-built wiring). |
| 1.2 | 2026-04-20 | Wiring note: pointer to backward ladder **§C.2** (approximation vs exact retrieval). |
| 1.3 | 2026-04-20 | Companion: **§0** binding **trade** / **learned behavior** definitions. |
| 1.4 | 2026-04-20 | D3: **`student_context_annex_v1`** + `validate_student_context_annex_v1` pointer. |
