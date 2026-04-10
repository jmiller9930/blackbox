# basetrade — lab testing (Pyth + **Jupiter policy baseline**)

**Venue:** **Jupiter trade policy** only for current operator work. Deprecated venue paths are not used for proof — see [`docs/architect/ANNA_GOES_TO_SCHOOL.md`](../docs/architect/ANNA_GOES_TO_SCHOOL.md).

### Single story of truth (operator)

For **baseline**, the **binary** question — *for this `market_event_id`, did we post “trade permitted” vs “no trade”?* — is answered in **one place**: the **execution ledger** (`policy_evaluations` + baseline `execution_trades` when a trade exists). **Canonical market bars** live in **market SQLite** (`market_bars_5m`); the **bridge/tick** runs policy on new closed bars and **writes** that decision (including structured **`features` / `tile`** for the operator tile) into the ledger. The dashboard should reflect **that posted row**, not a second parallel “truth” from ad-hoc recompute.

The **§3 harness** below runs **`evaluate_sean_jupiter_baseline_v1`** on bars for **parity / testing**; **operator truth** is still **whatever the bridge persisted** to the ledger for each bar.

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

Tests **`evaluate_sean_jupiter_baseline_v1`** (thin adapter over **Jupiter_2**: ``jupiter_2_sean_policy`` — RSI 52/48, Supertrend 10/3, EMA200, ATR ratio) against **`data/sqlite/market_data.db`** (`market_bars_5m`). Needs **≥216** closed bars (`MIN_BARS`). Use on **clawbot** after `git pull` so code matches `main`.

**Canonical operator rules** (Signal Breakdown + ATR / extreme RSI order): [`docs/trading/jupiter_2_baseline_operator_rules.md`](../docs/trading/jupiter_2_baseline_operator_rules.md).

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

### Baseline ledger vs ingest (operator)

Hermes/Pyth ingest closes a 5m bucket and upserts `market_bars_5m` via `refresh_last_closed_bar_from_ticks`. **After each successful upsert**, the same path calls `run_baseline_ledger_bridge_tick` so **`policy_evaluations`** (full policy/tile payload for the operator surface) and baseline **`execution_trades`** stay aligned with the tape — **not only** when the Karpathy loop daemon runs. If those writes are missing or incomplete, the UI cannot claim a single posted story for that bar until persistence is fixed.

- **`BASELINE_LEDGER_AFTER_CANONICAL_BAR`** — default **on** (`1`). Set to `0` to skip the hook (unit tests do this; rare prod use).
- **`BLACKBOX_EXECUTION_LEDGER_PATH`** — should point at the same `execution_ledger.db` the dashboard and audits use (default `data/sqlite/execution_ledger.db` under repo root).
- **`BASELINE_LEDGER_BRIDGE`** — must stay **on** (`1`) for writes; same as above.

If `policy_evaluations` upserts hit a locked ledger, the bridge logs to stderr and may include `policy_evaluation_write_error` on the returned dict; fix SQLite contention or paths rather than ignoring silent gaps.

## 4) Sync on **clawbot** (`~/blackbox`)

Local edits do not update the server until Git is synced.

1. Push from your machine: `git push origin main` (or your branch).
2. On **clawbot**: `cd ~/blackbox && git pull origin main`
3. Run §3 from `~/blackbox`.

See [`docs/architect/local_remote_development_workflow.md`](../docs/architect/local_remote_development_workflow.md).

## 5) `trading_core` npm dependencies

`trading_core/package.json` lists historical SDK imports. **Jupiter policy** proof for baseline uses **§3** (Python), not npm alone.
