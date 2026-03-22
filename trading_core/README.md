# `trading_core` — rules source (Drift bot)

This folder holds the **canonical TypeScript snapshot** of the live-style **Drift SOL-PERP** bot — the **operational rules** (signals, sizing, orders, trailing, gates) you asked to preserve for building a smarter/dynamic system around.

| File | Purpose |
|------|---------|
| **`drift_trading_bot_source.ts`** | Full source extracted from the 2026-03-22 operator thread. |

**Secrets:** The original paste included a **tokenized QuickNode URL**. In git it is replaced with **`process.env.SOLANA_RPC_URL`** + public mainnet fallback. Export `SOLANA_RPC_URL` when running locally. **`keypair.json`** stays out of git.

**Higher-level narrative + gaps vs architect layers:** [`../docs/trading/REFERENCE_CURRENT_DRIFT_BOT.md`](../docs/trading/REFERENCE_CURRENT_DRIFT_BOT.md)
