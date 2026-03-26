# `trading_core` — rules source (Drift bot)

This folder holds the **canonical TypeScript snapshot** of the live-style **Drift SOL-PERP** bot — the **operational rules** (signals, sizing, orders, trailing, gates) you asked to preserve for building a smarter/dynamic system around.

| File | Purpose |
|------|---------|
| **`drift_trading_bot_source.ts`** | Full source extracted from the 2026-03-22 operator thread. |

**Secrets:** The original paste included a **tokenized QuickNode URL**. In git it is replaced with **`process.env.SOLANA_RPC_URL`** + public mainnet fallback. Export `SOLANA_RPC_URL` when running locally. **`keypair.json`** stays out of git.

### Create a Solana wallet (CLI)

From **repo root** (simplest — no `cd` into `trading_core`):

```bash
npm run create-wallet
```

Or from `trading_core/`:

```bash
cd trading_core
npm install
npm run create-wallet
```

**Do not use `sudo cd …`** — `cd` in a `sudo` subshell does not change your shell’s directory, so `npm` will run in the wrong folder and look for `package.json` at the repo root. Use plain `cd trading_core` (no sudo).

This writes **`keypair.json`** as a **JSON byte array only** — the format `drift_trading_bot_source.ts` loads (`Keypair.fromSecretKey`). It also writes **`wallet-backup.json`** (public key + base58 + array). **Do not commit** either file. To echo base58 once for a password manager: `SHOW_SECRET=1 npm run create-wallet`.

**Higher-level narrative + gaps vs architect layers:** [`../docs/trading/REFERENCE_CURRENT_DRIFT_BOT.md`](../docs/trading/REFERENCE_CURRENT_DRIFT_BOT.md)
