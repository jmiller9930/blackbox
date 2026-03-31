# Reference — Current Drift / SOL perp trading bot (as of 2026-03)

This document is the **in-repo handoff** for what the **live-style** trading bot does today, how it fits the **broader BLACK BOX vision** (multi-agent, learning, reflection, improving outcomes), and what **must never** be committed (keys, RPC auth URLs).

**Updated strategy spec (ATR + Supertrend + EMA200 + RSI + ATR ratio filter):** [`SOL_PERP_TREND_STRATEGY_SPEC_v2.md`](SOL_PERP_TREND_STRATEGY_SPEC_v2.md). **Python mirror (signals only, no execution):** [`../../strategy/sol_perp_signal.py`](../../strategy/sol_perp_signal.py).

**Sources:** Architect trading-system update (`docs/architect/architect_update_trading_system.md`), operator context, and a **code snapshot** shared 2026-03-22 (Sean S → John Miller; subject referenced **“trading bot code 60/40”** — meaning of **60/40** should be confirmed with the team, e.g. revenue vs effort split).

**Full source in-repo:** [`../../trading_core/drift_trading_bot_source.ts`](../../trading_core/drift_trading_bot_source.ts) (QuickNode URL redacted → `SOLANA_RPC_URL`).

---

## Vision (why this repo exists)

The **whole project** is aimed at a **team of agents** that:

- Work **together** (clear roles: analysis vs execution vs consultation — see architect doc).
- **Learn** from **context** and **reflection** (record signals, confidence, execution, outcomes).
- **Improve over time** (calibration, scoring, better trade quality — **not** “just use a bigger model”).

The **current bot** below is **one executable slice**: a **single-process TypeScript** Drift client. It is **not** yet the full multi-agent / learning stack; it is the **baseline execution + signal** path to evolve.

---

## Stack (verified from code snapshot)

| Layer | Technology |
|--------|------------|
| Chain / protocol | **Solana mainnet**, **Drift** (`@drift-labs/sdk`) |
| Market | **SOL-PERP** (index `0`), USDC spot index `0` |
| Price feed | **Pyth** via **SSE** (`hermes.pyth.network` stream — **do not embed secrets in docs**) |
| Order book / WS | **Drift DLOB** WebSocket (`dlob.drift.trade`) |
| Historical candles | Drift **Data API** (`data.api.drift.trade` … `SOL-PERP` 5m) |
| Volume gate | **CoinGecko** Drift exchange volume + BTC/USD (for USD normalization) |
| Wallet | Local **`keypair.json`** (must stay **out of git** and off chat logs) |
| RPC | **QuickNode** (or equivalent) Solana HTTP — **use env / secrets file; never commit tokenized URL** |

---

## Strategy summary (behavioral model)

> **2026-03 update:** The **authoritative** trend-bot rules (Supertrend (10,3), EMA200, RSI 14 with long/short thresholds, **ATR ratio ≥ 1.35** filter, dynamic risk 1%/2%/3%, ATR stops 1.6/2.8/4.0×) are in [`SOL_PERP_TREND_STRATEGY_SPEC_v2.md`](SOL_PERP_TREND_STRATEGY_SPEC_v2.md). The numbered list **below** is from an **older** snapshot (RSI swing-style); keep it only for historical comparison until the TS file is fully reconciled to v2.

1. **Signals (5-minute candles)** — *legacy snapshot*  
   - Build **5m candles** from **Pyth** tick stream; optionally **seed** from Drift Data API historical candles for RSI warmup.  
   - **RSI** (default period **14**) on close series.  
   - **Short:** prior candle **higher high** + RSI **dropped** vs previous bar + RSI **> 60** (and epsilon checks on price/RSI).  
   - **Long:** prior candle **lower low** + RSI **rose** vs previous bar + RSI **< 40**.  
   - Signals attach to **`pendingSignal`** and run when **flat**.

2. **Liquidity / participation gate**  
   - **24h volume** (via CoinGecko path in code) must exceed **`MIN_VOLUME_USD`** (e.g. **90M USD** in snapshot — tune carefully).  
   - **Book depth:** cumulative notional top **5** levels vs **`MIN_NOTIONAL_DEPTH_USD`** decides **limit vs market** entry/exit.

3. **Sizing**  
   - **`INITIAL_COLLATERAL`** × **`LEVERAGE`** (e.g. **20 × 40**) capped by **free collateral**, margin fraction, **`MARGIN_BUFFER`**.

4. **Position management**  
   - On fill / adoption: place **reduce-only** **SL** (trigger limit), **TP** (trigger limit), **emergency SL** (trigger market).  
   - **Trailing:** updates **TP**, **SL**, **emergency SL** from **Pyth** price moves; **breakeven lock** after **`SAFE_PROFIT_THRESHOLD`**.  
   - **Debounce / delays** between modify batches (`MOD_DEBOUNCE_MS`, `MOD_DELAY_MS`).  
   - **Conflict / flip:** opposite signal can **`closePosition`** with flip flag.

5. **Safety / housekeeping**  
   - **Entry timeout** cancels if no fill.  
   - **Adopt** external open position and re-place protectors.  
   - **Cancel remnants** on close; periodic check when flat.  
   - **SIGINT:** attempt orderly close + cancel + unsubscribe.

---

## Important constants (from snapshot — verify in code before relying)

Examples present in the shared source (names may drift if you paste a newer file):

- **Risk / exits:** `TP_PCT`, `SL_PCT`, `EMERGENCY_SL_PCT`, `BE_THRESHOLD`, `SAFE_PROFIT_THRESHOLD`, trailing min moves (`MIN_TRAIL_MOVE_PCT`, `MIN_SL_TRAIL_MOVE_PCT`).  
- **RSI:** `RSI_PERIOD`, `RSI_SHORT_THRESHOLD`, `RSI_LONG_THRESHOLD`, `RSI_EPSILON`, `PRICE_EPSILON`.  
- **Confidence:** `CONFIDENCE_THRESHOLD` on **Pyth** price (skip wide conf / bad tick).  
- **Timing:** `ENTRY_TIMEOUT_MS`, `POSITION_CHECK_INTERVAL_MS`, `VOLUME_CHECK_INTERVAL_MS`.  
- **Slippage / precision:** `SLIPPAGE_PCT`, Drift precisions (`BASE_PRECISION`, `PRICE_PRECISION`, etc.).

---

## Gaps vs architect “locked” architecture

| Architect layer | This bot (today) |
|-----------------|------------------|
| **Analyst** (structured JSON signal) | **Implicit** in RSI + candle rules; **not** the standardized `{ action, confidence, reasoning, context }` contract yet. |
| **Executor** (never invents signals) | **Same process** does signal + execution — **not split**. |
| **Consultant** (API escalation) | **Not present**. |
| **Learning loop** (record every trade + outcome) | **Logging only** to console; **no** durable store / scoreboard. |
| **Router / model picker** | N/A (not LLM-driven). |

Next evolution steps align with **`docs/architect/architect_update_trading_system.md`**: split roles, add storage, then consultant + router.

---

## Security & ops (non-negotiable)

- **Never** commit: `keypair.json`, **tokenized RPC URLs**, private API keys, or **raw** Quiknode paths.  
- Treat **mainnet** keys as **production secrets**; use **env vars** or a **secrets manager** for RPC and third-party URLs if they contain auth.  
- This reference **intentionally omits** full source listing; keep **canonical code** in a **private** repo or path agreed by the team, with **.gitignore** for keys.

## Billy -> Drift connection contract (`v1`)

For BLACK BOX `v1`, Billy is the Drift-facing execution bot. The connection path must be explicit, replayable, and secret-safe.

Required connection sequence:

1. load the wallet secret from `KEYPAIR_PATH`
2. parse the secret key as a 64-byte Solana keypair array
3. derive the wallet public key in code
4. compare the derived public key to the configured expected public key
5. create Solana `Connection` using `SOLANA_RPC_URL`
6. construct `AnchorWallet`
7. construct `DriftClient`
8. call `subscribe()`
9. if user account does not exist, call `initializeUserAccount()`
10. if margin is not enabled, call `updateUserMarginTradingEnabled([{ marginTradingEnabled: true, subAccountId: 0 }])`
11. confirm target market metadata is readable before treating Billy as Drift-ready

The in-repo snapshot already demonstrates the core SDK sequence:

```144:179:trading_core/drift_trading_bot_source.ts
public async initDrift() {
  ...
  const keypairJson = await fs.readFile(KEYPAIR_PATH, 'utf-8');
  const keypairArray = JSON.parse(keypairJson);
  const keypair = Keypair.fromSecretKey(Uint8Array.from(keypairArray));
  const wallet = new AnchorWallet(keypair);

  this.driftClient = new DriftClient({
    connection,
    wallet,
    env: 'mainnet-beta',
    perpMarketIndexes: [SOL_PERP_INDEX],
    spotMarketIndexes: [USDC_SPOT_INDEX],
    ...
  });
  await this.driftClient.subscribe();
  if (!await this.checkUserAccountExists()) {
    await this.driftClient.initializeUserAccount();
  }
  const userAccount = this.driftClient.getUserAccount();
  if (userAccount && !userAccount.isMarginTradingEnabled) {
    await this.driftClient.updateUserMarginTradingEnabled([{ marginTradingEnabled: true, subAccountId: 0 }]);
  }
```

Public Drift SDK references validating the onboarding surface:

- Drift docs: [Drift for Developers](https://docs.drift.trade/sdk-documentation)
- TypeScript SDK: [DriftClient](https://drift-labs.github.io/protocol-v2/sdk/classes/DriftClient.html)

Required proof pattern:

- `doctor` phase: prove wallet load, public-key match, RPC reachability, Drift subscribe success, readable user/market state, and no order placement
- `activate` phase: initialize user account and/or enable margin only if needed; still no order placement
- both phases must leave replayable command/output evidence in `docs/working/shared_coordination_log.md`

---

## Relation to BLACK BOX repo

- **`blackbox`** currently centers **Cody / OpenClaw** and **documentation**; the **Drift bot** may live **elsewhere** or be imported later.  
- This file gives **one shared truth** for **what the trading bot is** until code is vendored here (if ever).

---

*Last updated: 2026-03-22 — align with architect docs and operator snapshot.*
