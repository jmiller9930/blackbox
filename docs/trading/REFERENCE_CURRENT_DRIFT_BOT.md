# Reference — Current Drift / SOL perp trading bot (as of 2026-03)

This document is the **in-repo handoff** for what the **live-style** trading bot does today, how it fits the **broader BLACK BOX vision** (multi-agent, learning, reflection, improving outcomes), and what **must never** be committed (keys, RPC auth URLs).

**Sources:** Architect trading-system update (`docs/architect/architect_update_trading_system.md`), operator context, and a **code snapshot** shared 2026-03-22 (Sean S → John Miller; subject referenced **“trading bot code 60/40”** — meaning of **60/40** should be confirmed with the team, e.g. revenue vs effort split).

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

1. **Signals (5-minute candles)**  
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

---

## Relation to BLACK BOX repo

- **`blackbox`** currently centers **Cody / OpenClaw** and **documentation**; the **Drift bot** may live **elsewhere** or be imported later.  
- This file gives **one shared truth** for **what the trading bot is** until code is vendored here (if ever).

---

*Last updated: 2026-03-22 — align with architect docs and operator snapshot.*
