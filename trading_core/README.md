# `trading_core` — rules source (SOL perp bot)

This folder holds the **canonical TypeScript snapshot** of the live-style **SOL-PERP** bot — **Sean’s trading logic** in the sense of **operational rules** (signals, sizing, orders, trailing, gates) to preserve for a smarter/dynamic system around it.

**How to read it:** that logic is **strategy / mechanics**, not “the” trade policy. **Trade policy** = which venue binds settlement (**Jupiter Perps** vs historical **Drift**). **Operator posture:** there is **only one active trade policy — Jupiter Perps** (hook **Jack**). **Drift** is deprecated and not in service; the **Drift-shaped** monolith file is a **historical** snapshot, not a parallel live policy.

**Default routing in code:** `DEFAULT_VENUE_ID` → **Jupiter Perps** → **Jack** (`src/venue/adapter_model.ts`). **Billy** exists only for the **deprecated** Drift policy type in the type system and legacy prose.

**Terminology:** **Billy** / **Jack** are **hooks** (executors) into **Drift** vs **Jupiter** policy types — not interchangeable names for “the bot.” For **active** work, **Jack / Jupiter** only.

## Anna, Billy, Jack, and venues (clear as day)

| Agent | Trade policy (venue) | Role |
|--------|------------------------|------|
| **Anna** | (analyst) | Signals and confidence; **routes** approved execution packets by **venue / policy** — **not** free-text “use Jupiter.” |
| **Billy** | **Drift** only | **Hook:** Drift orders and positions (deprecated path). |
| **Jack** | **Jupiter Perps** only | **Hook:** Jupiter Perps orders and positions. |

**Rule:** One **hook** per intent — Anna sends **Drift**-policy work to **Billy**, **Jupiter Perps**-policy work to **Jack**. That keeps policy, venues, and humans aligned (`agents/agent_registry.json`).

**Adapter rule:** Drift and Jupiter code stay **separate** under `src/venue/` — no mixed SDK imports.

**Jupiter vs Drift — different path, not a skin:** Same L1 doesn’t mean the same integration. **Program**, **accounts**, **instructions**, **SDK**, and **subscriptions** differ; the monolith in `src/bot/` is **Drift-shaped** today. **Jack** needs a **Jupiter-native** client path (see `jupiter_perp.ts` anchors), not Drift calls with different constants.

**Where this is spelled in code:** [`src/venue/adapter_model.ts`](src/venue/adapter_model.ts) (`VenueId`, `executorForVenue`).

**Parity with Python:** `modules/execution_adapter/` — same handoff shape; wire `executor_agent_id` / lane to Billy vs Jack adapters as implementation lands.

**Today’s snapshot:** `src/bot/drift_trading_bot_source.ts` is still a **monolith** (strategy + **Drift** SDK). Jupiter is **IDs only** in `jupiter_perp.ts` until **Jack’s** adapter is implemented. Splitting **strategy** vs **venue** is the target shape.

| Path | Purpose |
|------|---------|
| **`src/bot/drift_trading_bot_source.ts`** | Full bot — extracted from the 2026-03-22 operator thread. |
| **`src/venue/adapter_model.ts`** | `VenueId`, `executorForVenue` (Billy↔Drift, Jack↔Jupiter). |
| **`src/venue/jupiter_perp.ts`** | Jupiter Perps program / pool / custody `PublicKey`s (Sean). |
| **`scripts/create-solana-wallet.ts`** | CLI: write `keypair.json` + `keypair.base58` (`npm run create-wallet`). |

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

This writes **`keypair.json`** — **one line**, compact `[n,n,...]` (no spaces) for `src/bot/drift_trading_bot_source.ts`. It also writes **`keypair.base58`** — **one line**, base58 only (no `[]` / `{}`) for wallet import UIs. **Do not commit.** To print base58 once: `SHOW_SECRET=1 npm run create-wallet`.

Run the bot (after `npm install` in `trading_core/` and Drift SDK deps resolved): `npm run bot` from `trading_core/` (same cwd as `keypair.json` unless `KEYPAIR_PATH` is set).

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
