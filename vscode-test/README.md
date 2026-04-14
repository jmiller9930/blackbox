# vscode-test — lab / parity (Blackbox)

This directory holds **standalone** tooling that is **outside** the main Python application tree. It serves as an **analog** for parity-checking Blackbox: same **Binance financial REST** path (via host **WireGuard / Proton** split-tunnel), optional **wallet identity** (pubkey only), **paper-only** signals (no on-chain execution), and **onboard SQLite** for polls + paper analog events. **Sean V3 policy truth** remains in Python (`jupiter_3_sean_policy.py`); this stack logs ingest + stub rows for comparison.

Optional local **TypeScript** experiments (`superjup.ts`) are separate and not required for the Docker analog.

**Canonical remote host:** **`clawbot.a51.corp`**, repo checkout **`~/blackbox`**. After any doc change, **`git pull origin main`** on the server so paths match this file.

---

## Documentation map

### Primary — Docker container + clawbot

| Doc | What it covers |
|-----|----------------|
| **[`binance-klines-mini/README.md`](binance-klines-mini/README.md)** | What the image is; **path on clawbot** `~/blackbox/vscode-test/binance-klines-mini`; **deploy** (`git pull`, `docker compose up -d --build`); **`network_mode: host`**; logs; **`capture/`** (NDJSON + SQLite); **`run-backfill-clawbot.sh`**; **`jup_v3_parity_compare`** command |
| **[`binance-klines-mini/TURNOVER_NEXT_STEPS.md`](binance-klines-mini/TURNOVER_NEXT_STEPS.md)** | Handoff: `sean_parity.db`, architect mechanical checks, parity command, poller / 451 notes |
| **[`binance-klines-mini/docker-compose.yml`](binance-klines-mini/docker-compose.yml)** | Service env, volumes, inline comments |

### VPN / routing (required for Binance on the server)

Binance egress uses the **host** routing table (WireGuard **split-tunnel**). The container does **not** run VPN software inside the image.

| Doc / script | What it covers |
|--------------|----------------|
| **[`VPN/README.md`](../VPN/README.md)** | Split-tunnel model, Binance vs production NIC, **HTTP 451** when routing is wrong, `curl` checks |
| **[`scripts/clawbot/binance_api_route_via_proton_wg.sh`](../scripts/clawbot/binance_api_route_via_proton_wg.sh)** | Merge current **`api.binance.com`** IPs into **`wg-proton-mx`** when CDN prefixes drift (run on host, typically with `sudo`) |
| **[`scripts/clawbot/binance_api_knock_then_repair_if_needed.sh`](../scripts/clawbot/binance_api_knock_then_repair_if_needed.sh)** | Lightweight **`/api/v3/ping`** knock; invokes repair script if not HTTP 200 |
| **[`scripts/clawbot/install_binance_wg_route_timer.sh`](../scripts/clawbot/install_binance_wg_route_timer.sh)** | Optional systemd timer for periodic knock + repair |

### Python — Sean V3 policy vs parity tooling (main repo)

| Area | Path |
|------|------|
| Jupiter_3 policy | [`modules/anna_training/jupiter_3_sean_policy.py`](../modules/anna_training/jupiter_3_sean_policy.py) |
| Baseline adapter (`evaluate_sean_jupiter_baseline_v3`) | [`modules/anna_training/sean_jupiter_baseline_signal.py`](../modules/anna_training/sean_jupiter_baseline_signal.py) |
| Sean SQLite ↔ Blackbox compare | [`modules/anna_training/jup_v3_parity_compare.py`](../modules/anna_training/jup_v3_parity_compare.py) |

### TypeScript lab (optional; not the Docker image)

These files may exist only on a developer machine unless explicitly committed. They are **not** required for the **`binance-klines-mini`** container.

| File | Note |
|------|------|
| `superjup.ts` | Compile-safe stub; not deployed by default |
| `superjup.ts.old` | Legacy reference bot — **do not** use for current parity proof; Python + `binance-klines-mini` are authoritative |

---

## Fast path — get the container running on the server

```bash
cd ~/blackbox && git pull origin main
cd vscode-test/binance-klines-mini
docker compose up -d --build
```

Then read **[`binance-klines-mini/README.md`](binance-klines-mini/README.md)** first; use **[`binance-klines-mini/TURNOVER_NEXT_STEPS.md`](binance-klines-mini/TURNOVER_NEXT_STEPS.md)** for acceptance / parity follow-ups.

---

## Related Blackbox docs

- **[`docs/architect/local_remote_development_workflow.md`](../docs/architect/local_remote_development_workflow.md)** — local vs clawbot sync
- **[`UIUX.Web/docker-compose.yml`](../UIUX.Web/docker-compose.yml)** — dashboard stack; some services use host network for the same Binance routing reason (see comments there)
