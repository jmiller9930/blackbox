# basetrade — lab testing (Pyth + **Jupiter policy baseline**)

**Venue:** **Jupiter trade policy** only for current operator work. Deprecated venue paths are not used for proof — see [`docs/architect/ANNA_GOES_TO_SCHOOL.md`](../docs/architect/ANNA_GOES_TO_SCHOOL.md).

## 1) Pyth-only signal

Proves **Hermes SSE** for the **SOL/USD** feed used with canonical market ingest.

```bash
cd basetrade && npm install
node pyth_signal_probe.mjs 1800    # 30 minutes
node pyth_signal_probe.mjs 3600    # 1 hour
```

Exit 0 if messages were received; logs under your terminal (add `tee` if you want a file).

## 2) Historical `trading_core` bot (`npm run bot`)

Legacy snapshot; **not** the Jupiter proof path. Prefer §3 for baseline parity.

```bash
./basetrade/run_shadow_bot.sh 1800   # 30 min (from repo root)
```

After a run:

```bash
python3 basetrade/summarize_log.py basetrade/logs/shadow_bot_*.log
```

## 3) **Jupiter policy — baseline signal test** (Python parity harness)

Tests **`evaluate_sean_jupiter_baseline_v1`** (Sean **Jupiter policy v2**: RSI 52/48 + Supertrend + EMA200, on top of aggregateCandles-style structure) against **`data/sqlite/market_data.db`** (`market_bars_5m`). Needs **≥200** closed bars. Use on **clawbot** after `git pull` so code matches `main`.

```bash
# From repo root (e.g. ~/blackbox on clawbot)
chmod +x basetrade/run_jupiter_baseline_test.sh
./basetrade/run_jupiter_baseline_test.sh
./basetrade/run_jupiter_baseline_test.sh --json
```

Optional: also run **`run_baseline_ledger_bridge_tick`** (may **write** `execution_trades` if `BASELINE_LEDGER_BRIDGE=1`):

```bash
BASELINE_LEDGER_BRIDGE=0 ./basetrade/run_jupiter_baseline_test.sh   # signal only, no ledger write
./basetrade/run_jupiter_baseline_test.sh --bridge-dry-run          # includes bridge result
```

Env:

- `BLACKBOX_MARKET_DATA_PATH` — override SQLite path (default `data/sqlite/market_data.db`).
- `BASELINE_LEDGER_SIGNAL_MODE` — default `sean_jupiter_v1`; `legacy_mechanical_long` for old bar-long only.

## 4) Sync on **clawbot** (`~/blackbox`)

Local edits do not update the server until Git is synced.

1. Push from your machine: `git push origin main` (or your branch).
2. On **clawbot**: `cd ~/blackbox && git pull origin main`
3. Run §3 from `~/blackbox`.

See [`docs/architect/local_remote_development_workflow.md`](../docs/architect/local_remote_development_workflow.md).

## 5) `trading_core` npm dependencies

`trading_core/package.json` lists historical SDK imports. **Jupiter policy** proof for baseline uses **§3** (Python), not npm alone.
