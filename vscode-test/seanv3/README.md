# seanv3 (Docker)

## What this project is for

**Purpose:** A **parity check** for **Blackbox**, not a second runtime that “drives” Blackbox.

- **Sean V3** (policy + this ingest sidecar) and **Blackbox** are **independent** processes. There is **no** direct connection between them.
- **Expected alignment:** The **same strategy** (Sean V3 / Jupiter_3) and the **same Binance API data** (same bars for the same `market_event_id` / candle open) should produce **matching decisions**:
  - If Sean V3 **would trade** on a bar, Blackbox should **also** show a trade (or equivalent “trade permitted” / execution path) for that policy lane.
  - If Sean V3 **would not trade**, Blackbox should **not** trade on that bar for that lane — **both flat** is the “in sync” outcome.

**How you prove it:** Compare **this service’s** SQLite + NDJSON (`capture/`) to Blackbox **`binance_strategy_bars_5m`**, **`policy_evaluations`**, and ledger rows (see **`modules/anna_training/jup_v3_parity_compare.py`** and repo parity docs). Mismatches mean Blackbox or ingest is **out of parity**, not that the container is “wrong” by default.

---

**What it does technically:** **Parity analog** — polls **Binance REST klines** over the **host** network (WireGuard / Proton **split-tunnel** for `api.binance.com`), optionally **connects a Solana wallet** (pubkey only in DB — secrets never logged), runs **paper-only** logging (no Jupiter program calls, no signed txs), and persists **analog data** to onboard **SQLite** beside NDJSON.

**Sean / Jupiter_3 authoritative policy logic** stays in **`modules/anna_training/jupiter_3_sean_policy.py`** inside Blackbox; this container records **ingest + analog events** so you can diff against Blackbox.

**Parent index:** [`../README.md`](../README.md) — VPN scripts, Python parity commands, fast path.

---

## What runs inside

| Concern | Behavior |
|---------|----------|
| **Financial API (Binance)** | HTTPS klines — must follow **host** routing (`network_mode: host`). No VPN client inside the container. |
| **Wallet** | Optional `KEYPAIR_PATH` → loads **pubkey** only; table `paper_wallet`. |
| **Trading** | **Paper only** — events in `paper_trade_log` (`binance_kline_ingest`, `paper_signal_stub`, `wallet_connected`, errors). No execution. |
| **Database** | Single SQLite file (`SQLITE_PATH`), same volume as capture. |

### SQLite tables (onboard)

| Table | Role |
|-------|------|
| `sean_binance_kline_poll` | Raw poll rows (parity vs `binance_strategy_bars_5m`). |
| `analog_meta` | Keys e.g. `wallet_status`, `last_stub_signal_open_ms`, `financial_api_routing` note. |
| `paper_wallet` | One row: connected pubkey + `paper_only=1`. |
| `paper_trade_log` | Append-only analog events (ingest, stub signal, wallet lifecycle). |

---

## Remote host (clawbot)

**Canonical path:** `~/blackbox/vscode-test/seanv3` on **`clawbot.a51.corp`**.

### Deploy / update

**One-command helper (recommended):** [`seanv3py`](./seanv3py) or `python3 seanv3.py` — see **[`SEANV3PY.md`](./SEANV3PY.md)** for the full **operator process** (deploy → disconnect SSH → reconnect → `status` → `console` tmux reattach).

Manual:

```bash
cd ~/blackbox && git pull origin main
cd vscode-test/seanv3
docker compose up -d --build
```

### Wallet (optional)

1. Place a Solana keypair JSON on the host under **`./capture/keypair.json`** (same byte array format as `solana-keygen`; file is git-ignored via `capture/.gitignore`).
2. Uncomment / set in `docker-compose.yml`:

   ```yaml
   KEYPAIR_PATH: /capture/keypair.json
   ```

3. Restart the stack. Check logs for `paper wallet pubkey: ...` and `paper_trade_log` rows `wallet_connected`.

### VPN rules for Binance (mandatory)

Sean V3 **must** follow the same **clawbot host** rules as the rest of this repo for **`api.binance.com`** traffic:

| Rule | How this stack complies |
|------|---------------------------|
| Binance egress via **Proton WG** on the host (`wg-proton-mx`), not the production NIC alone | **`network_mode: host`** so this process uses the **kernel routing table** on clawbot (same path as `VPN/README.md` traffic model). |
| **No** VPN client inside the container | Image has **no** WireGuard/Proton packages — only `fetch()` to Binance. |
| **Do not** use default Docker **bridge** for production Binance calls here | **Do not** remove **`network_mode: host`** from `docker-compose.yml` for this service; bridge NAT can bypass split-tunnel and cause **HTTP 451**. |
| CDN / **`AllowedIPs`** drift on the host | Fix on the **host** with **`scripts/clawbot/binance_api_route_via_proton_wg.sh`** (see **`VPN/README.md`**). |

Authoritative doc: **[`VPN/README.md`](../../VPN/README.md)** (lab requirement, traffic model, scope).

**Backfill** (`./run-backfill-clawbot.sh`) uses **`docker compose run`** on the same **`seanv3`** service definition, so it inherits **`network_mode: host`** and the same Binance path as the long-running poller.

### Logs

```bash
cd ~/blackbox/vscode-test/seanv3
docker compose logs -f
```

### Artifacts (host, next to compose)

| Path | Purpose |
|------|---------|
| `./capture/seanv3.ndjson` | Append-only JSON lines per poll. |
| `./capture/sean_parity.db` | SQLite: klines poll + paper analog tables. |

### Environment (see `docker-compose.yml`)

| Variable | Purpose |
|----------|---------|
| `BINANCE_KLINES_URL` | Default public klines URL. |
| `POLL_INTERVAL_MS` | Default `300000` (5m); min 5s in code. |
| `CAPTURE_PATH`, `SQLITE_PATH` | NDJSON + DB under `/capture`. |
| `KEYPAIR_PATH` | Optional wallet JSON path inside container. |
| `PAPER_TRADING` | `1` (default) or `0` to skip paper/stub logging. |

### One-shot backfill (historical klines)

```bash
./run-backfill-clawbot.sh
# optional: LIMIT=1000 ./run-backfill-clawbot.sh
```

### Parity vs Blackbox (Python)

```bash
cd ~/blackbox
PYTHONPATH=. python3 -m modules.anna_training.jup_v3_parity_compare \
  vscode-test/seanv3/capture/sean_parity.db
```

Set `BLACKBOX_MARKET_DATA_PATH` if needed.

---

## Related docs

| Doc | Role |
|-----|------|
| **`../README.md`** | vscode-test index |
| **`TURNOVER_NEXT_STEPS.md`** | Architect checks, follow-ups |
| **`../../VPN/README.md`** | Split-tunnel |
| **`../../scripts/clawbot/binance_api_route_via_proton_wg.sh`** | Route repair |

## Source files

| File | Role |
|------|------|
| `app.mjs` | Poll loop, NDJSON, klines + paper analog |
| `paper_analog.mjs` | Schema + stub paper events |
| `wallet_connect.mjs` | Pubkey from keypair file |
| `backfill.mjs` | Historical klines |
| `run-backfill-clawbot.sh` | Host preflight + backfill |
