# binance-klines-mini (Docker)

Small **Node 22 Alpine** container that polls **Binance REST klines** (SOLUSDT 5m by default), writes **NDJSON** and optional **SQLite** for **Jupiter / Sean V3 parity** vs Blackbox ingest. It lives under `vscode-test/` but is **not** the TypeScript `superjup.ts` lab — that file is separate and is **not** run inside this image.

## Remote host (clawbot)

**Canonical path:** `~/blackbox/vscode-test/binance-klines-mini` on **`clawbot.a51.corp`** (or any host with Docker + the same repo layout).

### Deploy / update

```bash
cd ~/blackbox && git pull origin main
cd vscode-test/binance-klines-mini
docker compose up -d --build
```

### Why `network_mode: host`

Binance egress must use the **host routing table** (WireGuard **split-tunnel** to Binance-only prefixes). The default Docker bridge often does **not** follow that path and you may see **HTTP 451** or timeouts. See **`VPN/README.md`** at repo root.

### Logs

```bash
cd ~/blackbox/vscode-test/binance-klines-mini
docker compose logs -f
```

Expect JSON lines with `"ok":true`, `latencyMs`, and `kline` OHLCV. Sustained **451** → fix VPN / routes, not the app.

### Artifacts (host, next to compose)

| Path | Purpose |
|------|---------|
| `./capture/binance_klines.ndjson` | Append-only JSON lines per poll (`CAPTURE_PATH`). |
| `./capture/sean_parity.db` | SQLite table `sean_binance_kline_poll` (`SQLITE_PATH`) for parity vs `binance_strategy_bars_5m`. |

### Environment (see `docker-compose.yml`)

- `BINANCE_KLINES_URL` — default public klines URL.
- `POLL_INTERVAL_MS` — default `300000` (5 minutes); minimum enforced in code is 5s.
- `CAPTURE_PATH`, `SQLITE_PATH` — optional; compose sets both under `/capture`.

### One-shot backfill (historical klines)

From **this directory** on the host (preflights Binance ping = 200):

```bash
./run-backfill-clawbot.sh
# optional: LIMIT=1000 ./run-backfill-clawbot.sh
```

### Parity vs Blackbox (Python)

From **repo root** `~/blackbox`:

```bash
PYTHONPATH=. python3 -m modules.anna_training.jup_v3_parity_compare \
  vscode-test/binance-klines-mini/capture/sean_parity.db
```

Set `BLACKBOX_MARKET_DATA_PATH` if market DB is not `data/sqlite/market_data.db`.

## Related docs

- **`TURNOVER_NEXT_STEPS.md`** — architect checks, row counts, next steps.
- **`VPN/README.md`** — split-tunnel / Binance-only WireGuard rules.

## Files

| File | Role |
|------|------|
| `Dockerfile` | `node:22-alpine`, `node --experimental-sqlite app.mjs` |
| `app.mjs` | Poll loop, NDJSON + SQLite inserts |
| `backfill.mjs` | One-shot historical klines into SQLite |
| `run-backfill-clawbot.sh` | Host preflight + `docker compose run` backfill |
