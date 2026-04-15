# SeanV3 (Docker) — **standalone application**

SeanV3 is **its own application** in this repo: **`vscode-test/seanv3/`** (Node, Docker). It does **not** run inside or import the BlackBox application pod. Strategy, data, ledger, and reporting are **SeanV3-owned**.

**Operator initiative:** use the **SeanV3 operator TUI** — `scripts/operator/preflight_pyth_tui.py` (preflight, policy slots, oracle context, **wallet** pubkey from `paper_wallet` in `capture/sean_parity.db`, **paper account summary**, **trade window**, **parity**). Use **`--actual`** (or `SEANV3_TUI_ACTUAL=1`) for a **live-capital intent** banner; that flag is display-only — moving off paper in the container is **`PAPER_TRADING=0`** in compose/env (on-chain execution is a separate product step). Not a BlackBox dashboard.

**Optional, separate concern:** other systems in the monorepo may **compare** artifacts to SeanV3 **after** SeanV3 is complete on its own. That is **not** part of SeanV3 runtime and **not** required to operate SeanV3.

**Design risk to avoid:** Folding SeanV3 into “training” or “anna” paths mentally — those are **other** trees. SeanV3 code and operator flow stay under **`seanv3/`** + **`scripts/operator/`** for the TUI.

### Same server as BlackBox UI (UIUX.Web)

You can run **both** on one host. BlackBox **nginx** (`UIUX.Web` compose) binds **443** (and **80**); the **`api`** service uses **host network** and listens on **:8080**. The SeanV3 **poll/engine** container (`seanv3`) does not bind HTTP; **Jupiter** (`jupiter-web`) binds **:707** on the host (`network_mode: host`), so it **does not use 443**. (`jupiter-web` runs as root in compose so Node can bind port **707** on Linux.) Start each stack from its directory:

- `cd UIUX.Web && docker compose up -d` (or your usual command)
- `cd vscode-test/seanv3 && docker compose up -d --build`

Both rely on the **host** routing table for Binance (WireGuard split-tunnel on clawbot per `VPN/README.md`).

**Jupiter** (read-only web app; container **`jupiter-web`):** binds **HTTP** on **707** on the **lab host** (no TLS in the Node app). **`/`** = front door (Jupiter image + link). **`/dashboard`** = full operator UI (TUI parity). **Operator browser:** **`http://clawbot.a51.corp:707/dashboard`** on VPN/LAN, or **`http://jupv3.greyllc.net:737/dashboard`** (same port forward). **Proof from your machine (VPN):** `curl -sS http://clawbot.a51.corp:707/health` — same URL class as the browser, **not** loopback on your laptop. Default **`JUPITER_WEB_PORT=707`**. Public path: **WAN :737 → LAN :707**. **`/api/summary.json`**, wallet, position, trades. Deploy on **clawbot:** `docker compose up -d` in this directory. Editor-only dev clone: **`npm run jupiter`** (may need **`sudo`** for **707** on Linux).

**Browser login (optional):** compose loads **`vscode-test/lab_dashboard_login.defaults.env`**, which sets **`JUPITER_WEB_LOGIN_USER`** / **`JUPITER_WEB_LOGIN_PASSWORD`**. When both are non-empty, **jupiter-web** enforces **HTTP Basic Auth** on every route except **`GET /health`** (probes). Override locally with a gitignored **`vscode-test/lab_dashboard_login.env`** (see repo root `.gitignore`). This is **not** the same secret as **`JUPITER_OPERATOR_TOKEN`** (Bearer for API POSTs).

**Dashboard UX:** default **`JUPITER_WEB_LIVE_POLL=1`** — client **`fetch`**es **`/api/summary.json`** on **`JUPITER_WEB_REFRESH_SEC`** interval and updates the DOM (no `<meta refresh>` flicker). Set **`JUPITER_WEB_LIVE_POLL=0`** to fall back to full-page auto-refresh. WebSocket not required; SSE possible later.

**API contract (Jupiter):** observability (**`GET`**) + **one controlled write**: **set active Jupiter policy**. Reads are open within your network policy; **`JUPITER_WEB_READ_ONLY=1`** (default on **`jupiter-web`**) blocks **`POST /api/operator/*`** (wallet, funding, stake). The **sole write** is **`POST /api/v1/jupiter/active-policy`** (alias **`POST /api/v1/jupiter/set-policy`**) with **`Authorization: Bearer`** and body **exactly** **`{"policy":"jup_v4"}`** (or **`jup_v3`**, **`jup_mc_test`**). That endpoint only validates the id against the shipped module set, records **`analog_meta.jupiter_active_policy`**, and the engine applies it on the **next cycle** — it does **not** mutate trade history, rewrite bars, bypass lifecycle, or load arbitrary code. **`GET /api/v1/jupiter/policy`** returns **`contract`**, **`allowed_policies`**, and the active id. Compose loads **`lab_operator_token.env`**. Set **`JUPITER_WEB_READ_ONLY=0`** to re-enable dashboard wallet POSTs. Bearer is **not** a Solana wallet key.

**Trades (Sean paper):** dashboard **Trade window** — jump dropdown, row click → JSON snapshot, **`GET /api/v1/sean/trades.csv`** export (standard columns + full **`metadata_json`**). Per-trade: **`GET /api/v1/sean/trade/<id>.json`**. Baseline BlackBox “trade synthesis” / execution-ledger tiles are separate; export those from the baseline UI if needed.

**Parity (Jupiter vs BlackBox):** table columns are **Jupiter** / **BlackBox**. When Jupiter’s active policy ≠ **`JUPITER_PARITY_ALIGNED_POLICY`** (default **`jup_v4`**), the **Parity** column is **blank** (baseline compare not meaningful). Set the env on **`jupiter-web`** to match your policy when you want row-by-row parity text.

**Web vs TUI (same backend, two displays):** see [`JUPITER_WEB_TUI_ALIGNMENT.md`](JUPITER_WEB_TUI_ALIGNMENT.md). The Jupiter page mirrors `preflight_pyth_tui.py` panels (preflight, policy, wallet, paper ledger, parity, trades, oracle). Compose mounts **`../../` → `/repo:ro`** for policy registry + execution ledger; override **`JUPITER_WEB_REFRESH_SEC`** (default `3`, `0` disables HTML auto-refresh).

**Troubleshooting — browser says “problem” / can’t load :707**

1. **Use `http://` only.** Jupiter does **not** speak TLS on 707. **`https://…:707`** will fail—use **`http://clawbot.a51.corp:707/`** (or your public URL).
2. **Prove reachability the same way everywhere:** `curl -sS http://clawbot.a51.corp:707/health` from any machine on VPN/LAN (expect JSON with `"ok":true`). Or over SSH in one shot: `ssh jmiller@clawbot.a51.corp 'curl -sS http://clawbot.a51.corp:707/health'`. If that fails, on **clawbot** run **`docker compose ps`** and **`docker logs jupiter-web --tail 80`** in **`~/blackbox/vscode-test/seanv3`**, then **`docker compose up -d --build`** after **`git pull`** succeeds.
3. **`jupsync.py`** uses the same default health URL (`JUPSYNC_JUPITER_HEALTH_URL`, default `http://clawbot.a51.corp:707/health`) on the remote host after deploy — not `127.0.0.1`.
4. If **`git pull`** on clawbot was blocked (e.g. untracked files), fix the merge and redeploy before re-testing.

### Lab deploy loop (`jupsync.py`)

**Consistent update process:** commit in your clone → **`python3 scripts/jupsync.py`** from repo root. That **pushes** to `origin`, **SSHs to clawbot**, **`git pull`** in `~/blackbox`, then **`docker compose up -d --build`** in **`vscode-test/seanv3`**. The script then **curls the lab health URL** (default **`http://clawbot.a51.corp:707/health`**, over SSH on the lab host — override with **`JUPSYNC_JUPITER_HEALTH_URL`**). **Verify in a browser** with the same host: **`http://clawbot.a51.corp:707/`**. Skip the health step with **`--skip-health`**.

- **`--dry-run`** — print actions only. **`--skip-push`** — you already pushed; only remote pull + compose.
- Same SSH/branch env vars as **`scripts/sync.py`** (`BLACKBOX_SYNC_SSH`, etc.); **`JUPSYNC_SSH`** / **`JUPSYNC_BRANCH`** override if needed.
- **BlackBox operator UI** (nginx/api under `UIUX.Web`) is **not** updated by `jupsync.py` — use **`scripts/sync.py`** for that.

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

### Paper account (testing — not real money)

- **`SEAN_PAPER_STARTING_BALANCE_USD`** (default **1000**) is the simulated **starting balance** in USD for operator psychology and reporting.
- On first SQLite init, the value is **stored** in `analog_meta.paper_starting_balance_usd` and treated as the account baseline.
- **Equity** ≈ starting + realized P&amp;L + **unrealized** (mark-to-market when a position is open). The TUI uses **Hermes** SOL/USD for mtm; **`report.mjs`** uses the **latest polled Binance close** as a mark proxy.
- **Engine sizing** is still **`SEAN_ENGINE_SIZE_NOTIONAL_SOL`** (P&amp;L math uses the same units as `computePnlUsd` in `sean_lifecycle.mjs`).

### SeanV3 vs BlackBox — “same policy” at the same time?

Reasonable **directional** expectation: both can run **Jupiter_3-style** Sean logic, but **bit-identical** trades at the same wall-clock instant are **not guaranteed** unless you align **all** of: **canonical bar source** (SeanV3 uses `sean_binance_kline_poll`; BlackBox uses `market_bars_5m` / ingest path), **bar closure / `market_event_id`**, **engine version**, **MIN_BARS** warmup, and **poll timing**. Use a **shared harness** or diff tool if you need strict parity proof — not the default operator path.

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

### Sean-native paper engine (`sean_jupiter4_engine_v1` / `sean_jupiter3_engine_v1`)

Runs after each kline insert when **`SEAN_ENGINE_SLICE`** is not `0`/`false`/`no` (name retained for compatibility).

- **Entry policy (runtime):** **`analog_meta.jupiter_active_policy`** is the primary source of truth (`jup_v4` | `jup_v3` | `jup_mc_test`). If unset, **`SEAN_JUPITER_POLICY`** is used (`jupiter_4` / `jupiter_3` / `jupiter_mc_test` aliases), then default **`jup_v4`**. The engine reads this **each processing cycle** (no long-lived cache). **Operator API:** `GET /api/v1/jupiter/policy`, `POST /api/v1/jupiter/active-policy` (alias `set-policy`) (Bearer `JUPITER_OPERATOR_TOKEN`). Dashboard: **Set active Jupiter policy**.
- **Exit:** `sean_lifecycle.mjs` — initial SL/TP from ATR×1.6 / ×4.0, breakeven +0.2%, monotonic trailing; OHLC bar hit test (both SL+TP → SL wins).
- **Dedup:** one step per `market_event_id` (`analog_meta.sean_engine_last_bar_mid`).
- **Tests:** `npm test` from this directory.

### SQLite tables (onboard)

| Table | Role |
|-------|------|
| `sean_binance_kline_poll` | Raw poll rows (Binance REST). |
| `sean_paper_position` | Single-row state: `side`, entry, **SL/TP**, `atr_entry`, `breakeven_applied`, `bars_held`, … |
| `sean_paper_trades` | Closed trades (`engine_id`, sides, times, prices, gross P&amp;L, `result_class`). |
| `analog_meta` | `sean_engine_last_bar_mid`, **`jupiter_active_policy`**, wallet keys, stub cursor. |
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
| `BINANCE_API_BASE_URL` | Binance REST origin (default `https://api.binance.com`); same env as BlackBox `public_data_urls`. Host routing: `VPN/README.md`. |
| `BINANCE_KLINES_URL` | Optional full klines URL override; if unset, built from `BINANCE_API_BASE_URL`. |
| `POLL_INTERVAL_MS` | Default `300000` (5m); min 5s in code. |
| `CAPTURE_PATH`, `SQLITE_PATH` | NDJSON + DB under `/capture`. |
| `KEYPAIR_PATH` | Optional wallet JSON path inside container. |
| `PAPER_TRADING` | `1` (default) or `0` to skip paper/stub logging. |
| `SEAN_PAPER_STARTING_BALANCE_USD` | Simulated account baseline for testing (default `1000`); stored in `analog_meta` on first run. |
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
