# Turnover — Sean Binance klines / parity DB (next steps)

## Where things stand

- **Host:** `clawbot.a51.corp`, repo `~/blackbox`.
- **Sean SQLite:** `vscode-test/binance-klines-mini/capture/sean_parity.db`, table `sean_binance_kline_poll`.
- **Backfill:** Use **`./run-backfill-clawbot.sh`** (preflights `https://api.binance.com/api/v3/ping` = HTTP 200, then `docker compose run` backfill). Requires **host WireGuard split-tunnel** for Binance; container uses **`network_mode: host`** so it follows host routing. See **`VPN/README.md`**.
- **BlackBox market OHLC:** `data/sqlite/market_data.db` (default `BLACKBOX_MARKET_DATA_PATH`), table `binance_strategy_bars_5m`.
- **Dashboard stack (UIUX.Web):** On clawbot, `api` + `binance-strategy-bars-sync` use **host network** so Binance traffic follows WireGuard; nginx proxies to `host.docker.internal:8080`. After compose changes: `cd UIUX.Web && docker compose up -d --build` (see `docker-compose.yml` header).

## Done recently (engineering)

- `network_mode: host` on `binance-klines` so egress matches host WG/Proton routing.
- `run-backfill-clawbot.sh` + compose comments; VPN doc for Binance-only egress.
- Successful backfill run on clawbot: **864** klines inserted (`LIMIT=864`, `SOLUSDT`). DB may show **865** rows if the poller inserted one extra bar — re-run mechanical checks and dedupe if governance requires exactly 864.

## Next steps (in order)

1. **Architect mechanical acceptance (five checks)** on `sean_parity.db`  
   - Row count (~864 expected).  
   - Continuity: consecutive distinct `candle_open_ms` differ by **300000** ms; count gaps.  
   - No duplicate `market_event_id`.  
   - Latest row: `market_event_id` + `close_px` vs `binance_strategy_bars_5m` for same `market_event_id` (float tolerance).  
   - Min/max `candle_open_ms` span ~**72h** (or `(rows-1)*5m` for contiguous series).  
   - Outcome must be **PASS** or **FAIL** with raw numbers — not “looks fine.”

2. **Parity compare (repo)** from `~/blackbox`:
   ```bash
   cd ~/blackbox && git pull origin main
   PYTHONPATH=. python3 -m modules.anna_training.jup_v3_parity_compare \
     vscode-test/binance-klines-mini/capture/sean_parity.db
   ```
   Set `BLACKBOX_MARKET_DATA_PATH` if market DB is not the default path.

3. **If row count must be exactly 864:** delete the extra poll row or stop the poller before backfill-only verification; document which `id` was removed.

4. **Ongoing poller:** `docker compose up -d` in `vscode-test/binance-klines-mini` — expect inserts every poll interval when Binance returns 200; confirm logs do not show sustained **451**.

5. **If Binance ping fails again:** fix WG **`AllowedIPs`** / split-tunnel so `api.binance.com` resolves to paths covered by policy routing (see **`VPN/README.md`** — CDN IPs move; ops may need prefix updates).

## Quick reference

| Artifact | Path |
|----------|------|
| Compose + service | `vscode-test/binance-klines-mini/docker-compose.yml` |
| Backfill script | `vscode-test/binance-klines-mini/run-backfill-clawbot.sh` |
| VPN / Binance egress | `VPN/README.md` |
| Parity module | `modules/anna_training/jup_v3_parity_compare.py` |
