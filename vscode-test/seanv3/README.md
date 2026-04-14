# SeanV3 (Docker) — **standalone application**

SeanV3 is **its own application** in this repo: **`vscode-test/seanv3/`** (Node, Docker). It does **not** run inside or import the BlackBox application pod. Strategy, data, ledger, and reporting are **SeanV3-owned**.

**Operator initiative:** use the **SeanV3 operator TUI** — `scripts/operator/preflight_pyth_tui.py` (preflight, policy slots, oracle context). That TUI is the primary shell for “is the SeanV3 stack healthy, what policy slot is active, what does Hermes show” — not a BlackBox dashboard.

**Optional, separate concern:** other systems in the monorepo may **compare** artifacts to SeanV3 **after** SeanV3 is complete on its own. That is **not** part of SeanV3 runtime and **not** required to operate SeanV3.

**Design risk to avoid:** Folding SeanV3 into “training” or “anna” paths mentally — those are **other** trees. SeanV3 code and operator flow stay under **`seanv3/`** + **`scripts/operator/`** for the TUI.

---

## Target components (SeanV3 as its own system)

| Layer | Requirement | Role in a complete SeanV3 |
|--------|-------------|---------------------------|
| **Market data** | Ingest and store **Binance 5m candles** in a **stable local store** with a **consistent `market_event_id`**. | Canonical bar tape for the engine. |
| **Strategy evaluation** | Run **Sean V3 logic** in **SeanV3** (this stack) against stored bars — enter / hold / exit / no-trade **without** calling other apps. | Implemented in **`vscode-test/seanv3/`** (Node); not Python, not another pod. |
| **Trade lifecycle** | **Open** a position object, **track** it, **close** per Sean V3 exit rules — not only bar-level yes/no. | Required for realistic P&amp;L and win/loss. |
| **Parity ledger** | Append **trade records** with enough detail for analysis: entry time/price, side, exit time/price, gross P&amp;L, optional net P&amp;L, result classification, strategy metadata. | Source of truth for SeanV3 outcomes. |
| **Reporting** | Trade list, win/loss counts, win rate, cumulative P&amp;L, per-trade detail (and optionally max drawdown later). | Operator and automation-facing. |
| **External compare (optional)** | **Last** — only if you explicitly run a separate compare job. | Not part of SeanV3; does not ship inside this container. |

---

## Current implementation status (honest)

| Layer | Status today |
|------|----------------|
| **Market data** | **Partial:** Binance klines poll + backfill into `sean_binance_kline_poll`, stable `market_event_id` in `app.mjs`. |
| **Strategy evaluation** | **Implemented in Node:** `jupiter_3_sean_policy.mjs` (EMA/RSI/BOS/volume/expected-move gates) + `sean_engine.mjs` on each **new** 5m bar. |
| **Trade lifecycle** | **Implemented:** ATR SL/TP (`sean_lifecycle.mjs`), breakeven, monotonic trailing, bar-range exit (SL wins if both touched). |
| **Sean trade ledger** | **`sean_paper_trades`** + `sean_ledger.mjs` (long/short, entry/exit, P&amp;L, `engine_id`). |
| **Legacy paper log** | `paper_trade_log` — ingest / stub / wallet; **not** the Sean trade ledger. |
| **Reporting** | **`npm run report`** or `node --experimental-sqlite report.mjs` — JSON summary + last 10 trades. |
| **External compare** | **Not part of SeanV3** — run only if you choose, from another context. |

**Implementation direction:** Harden **Sean-native** evaluation and **reporting** here; operator experience stays **TUI-first** (`scripts/operator/`).

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
| **Trading** | **Paper only** — Jupiter_3 signals + lifecycle write **`sean_paper_trades`**; **`paper_trade_log`** = ingest/stub/wallet. |
| **Database** | Single SQLite file (`SQLITE_PATH`), same volume as capture. |

### Sean-native paper engine (`sean_jupiter3_engine_v1`)

Runs after each kline insert when **`SEAN_ENGINE_SLICE`** is not `0`/`false`/`no` (name retained for compatibility).

- **Entry:** `jupiter_3_sean_policy.mjs` — same structure as the Python reference (min bars, gates, short-over-long if both fire).
- **Exit:** `sean_lifecycle.mjs` — initial SL/TP from ATR×1.6 / ×4.0, breakeven +0.2%, monotonic trailing; OHLC bar hit test (both SL+TP → SL wins).
- **Dedup:** one step per `market_event_id` (`analog_meta.sean_engine_last_bar_mid`).
- **Tests:** `npm test` from this directory.

### SQLite tables (onboard)

| Table | Role |
|-------|------|
| `sean_binance_kline_poll` | Raw poll rows (Binance REST). |
| `sean_paper_position` | Single-row state: `side`, entry, **SL/TP**, `atr_entry`, `breakeven_applied`, `bars_held`, … |
| `sean_paper_trades` | Closed trades (`engine_id`, sides, times, prices, gross P&amp;L, `result_class`). |
| `analog_meta` | `sean_engine_last_bar_mid`, wallet keys, stub cursor. |
| `paper_wallet` | Optional pubkey. |
| `paper_trade_log` | Legacy ingest/stub events. |

**Reporting:**

```bash
npm run report
# or
node --experimental-sqlite report.mjs --db ./capture/sean_parity.db
```

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
| `SEAN_ENGINE_SLICE` | `1` (default) enables Jupiter_3 engine; `0`/`false`/`no` disables. |
| `SEAN_ENGINE_SIZE_NOTIONAL_SOL` | Notional size multiplier for P&amp;L (default `1.0`). |

### One-shot backfill (historical klines)

```bash
./run-backfill-clawbot.sh
# optional: LIMIT=1000 ./run-backfill-clawbot.sh
```

### Optional — external compare (not SeanV3)

Some teams run a **separate** repo-root Python job to diff Sean SQLite against another system’s DB. That is **optional** and **not** required to build, run, or operate SeanV3. Do not treat it as SeanV3’s runtime.

---

## Related docs

| Doc | Role |
|-----|------|
| **`../README.md`** | vscode-test index |
| **[`../../scripts/operator/preflight_pyth_tui.py`](../../scripts/operator/preflight_pyth_tui.py)** | **SeanV3 operator TUI** (preflight, policy registry, Hermes panel) |
| **`TURNOVER_NEXT_STEPS.md`** | Supplementary checks (may reference optional compare tooling) |
| **`../../VPN/README.md`** | Split-tunnel |
| **`../../scripts/clawbot/binance_api_route_via_proton_wg.sh`** | Route repair |

## Source files

| File | Role |
|------|------|
| `app.mjs` | Poll loop, NDJSON, klines + paper analog + Sean engine slice |
| `jupiter_3_sean_policy.mjs` | Jupiter_3 Sean signal generation (Node) |
| `sean_lifecycle.mjs` | SL/TP, breakeven, trailing, exit evaluation |
| `sean_ledger.mjs` | Schema migrations + open/close/update position |
| `sean_engine.mjs` | Main loop: policy + lifecycle + ledger |
| `report.mjs` | CLI summary of `sean_paper_trades` |
| `paper_analog.mjs` | Legacy analog schema + stub paper events |
| `wallet_connect.mjs` | Pubkey from keypair file |
| `backfill.mjs` | Historical klines |
| `run-backfill-clawbot.sh` | Host preflight + backfill |
