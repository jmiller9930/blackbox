# `trading_core` — rules source (Drift bot)

This folder holds the **canonical TypeScript snapshot** of the live-style **Drift SOL-PERP** bot — the **operational rules** (signals, sizing, orders, trailing, gates) you asked to preserve for building a smarter/dynamic system around.

| File | Purpose |
|------|---------|
| **`drift_trading_bot_source.ts`** | Full source extracted from the 2026-03-22 operator thread. |

**Secrets:** The original paste included a **tokenized QuickNode URL**. In git it is replaced with **`process.env.SOLANA_RPC_URL`** + public mainnet fallback. Export `SOLANA_RPC_URL` when running locally.

**Key file:** The bot loads **`KEYPAIR_PATH`** (env) or defaults to **`keypair.json`** in the process working directory — JSON array of 64 bytes only. Put the file **only on your machine**; **never** paste or attach it to chat; **never** commit. You can point elsewhere, e.g. `export KEYPAIR_PATH="$HOME/.secrets/drift-keypair.json"`.

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

**Import an existing secret without echo (Python):** install **`base58`** once, then run from **repo root** (not inside `trading_core` — paths are relative to the blackbox folder):

```bash
cd ~/Documents/code_projects/blackbox
python3 -m pip install base58
python3 scripts/trading/import_solana_keypair.py -o trading_core/keypair.json
```

Or use the helper (always uses repo root):

```bash
bash scripts/trading/run_import_keypair.sh -o trading_core/keypair.json
```

Paste **base58** or a one-line **JSON array** `[...]` when prompted; input is **hidden**. **Do not** paste secrets into Cursor chat. Replace `~/Documents/code_projects/blackbox` with your real clone path if different.

**Higher-level narrative + gaps vs architect layers:** [`../docs/trading/REFERENCE_CURRENT_DRIFT_BOT.md`](../docs/trading/REFERENCE_CURRENT_DRIFT_BOT.md)
