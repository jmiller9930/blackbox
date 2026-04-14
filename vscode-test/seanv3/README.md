# seanv3 (Docker)

## Architectural principle (authoritative)

**BlackBox is one trade system. SeanV3 is another.** They must be designed so mismatches can be attributed to **one** system or the other, not to a fuzzy “parity harness.”

**SeanV3** must be a **standalone paper trade engine**: its own market data, its own evaluation, its own **trade lifecycle** (open → manage → close with Sean V3 exit rules), its own **ledger and reporting**. Only **after** that exists should **comparison** to BlackBox run as a **separate layer**, treating SeanV3 as an **independent reference path**, not as an extension of BlackBox.

The **operator TUI** (`scripts/operator/…`) sits **above** both: it can show health, paper P&amp;L, and **diff** BlackBox vs SeanV3 once both systems expose comparable artifacts.

**Design risk to avoid:** Treating SeanV3 as a thin ingest + stub that only answers isolated bar questions. That cannot produce trustworthy win/loss or P&amp;L, and it blames ambiguity on “parity” when the real gap is **incomplete SeanV3 structure**.

---

## Target components (SeanV3 as its own system)

| Layer | Requirement | Role in a complete SeanV3 |
|--------|-------------|---------------------------|
| **Market data** | Ingest and store **Binance 5m candles** in a **stable local store** with a **consistent `market_event_id`** (and aligned candle identity with BlackBox’s bar keying for later comparison). | Canonical bar tape for the engine. |
| **Strategy evaluation** | Run **Sean V3 logic** against **that stored data** and emit **trade decisions** (enter / hold / exit / no-trade) **inside SeanV3**, without depending on BlackBox runtime for the decision. | May share a **spec** with `modules/anna_training/jupiter_3_sean_policy.py`, but the **running engine** is SeanV3-owned. |
| **Trade lifecycle** | **Open** a position object, **track** it, **close** per Sean V3 exit rules — not only bar-level yes/no. | Required for realistic P&amp;L and win/loss. |
| **Parity ledger** | Append **trade records** with enough detail for analysis: entry time/price, side, exit time/price, gross P&amp;L, optional net P&amp;L, result classification, strategy metadata. | Source of truth for SeanV3 outcomes. |
| **Reporting** | Trade list, win/loss counts, win rate, cumulative P&amp;L, per-trade detail (and optionally max drawdown later). | Operator and automation-facing. |
| **Comparison** | **Last** — diff SeanV3 artifacts vs BlackBox **after** the above. | Uses the same comparison tools (`jup_v3_parity_compare`, etc.) as **reference vs reference**, not “helper vs master.” |

---

## Current implementation status (honest)

What exists **today** in this folder is **not yet** the full standalone engine above. It is **partial**:

| Layer | Status today |
|------|----------------|
| **Market data** | **Partial:** Binance klines poll + backfill into `sean_binance_kline_poll`, `market_event_id` helper in `app.mjs`. |
| **Strategy evaluation** | **Not standalone:** Policy truth for parity has been **Python-authoritative** (`jupiter_3_sean_policy.py` in BlackBox); this container does **not** yet run the full Sean V3 evaluator as a first-class engine loop. |
| **Trade lifecycle** | **Not implemented:** paper path is **ingest + stub / analog events**, not open/close position lifecycle with exit rules. |
| **Parity ledger** | **Partial:** `paper_trade_log` is event-oriented, not a full **trade ledger** with entry/exit/P&amp;L as specified above. |
| **Reporting** | **External / ad hoc:** NDJSON + SQLite queries; no dedicated SeanV3 reporting module yet. |
| **Comparison** | **Available** against BlackBox for **bars / stub signals** — **premature** as a verdict on “strategy parity” until lifecycle + ledger exist. |

**Implementation direction:** Evolve this repo into the **self-contained paper engine** (storage, decisions, lifecycle, ledger, reporting), **then** lock comparison as an independent layer.

---

## What this folder is for (operator + engineering)

**Purpose:** Deploy and run the **SeanV3 stack** on the lab host: **Binance REST** over **host** routing (WireGuard / Proton split-tunnel), optional wallet pubkey, **paper-only** (no signed chain txs), local **SQLite** + NDJSON under `capture/`.

**Historical note:** Earlier docs emphasized “parity analog” **ingest** first. The **architectural target** is now the **full SeanV3 system** in the table above; ingest remains the foundation.

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
