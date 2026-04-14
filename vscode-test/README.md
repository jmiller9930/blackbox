# vscode-test — SeanV3 lab (standalone application)

## What this is for

**SeanV3** is a **standalone application** under **`seanv3/`** (Node + Docker): its own Binance path, SQLite, paper engine, and ledger. It does **not** import or run inside the BlackBox application pod.

**Operator initiative:** the **SeanV3 operator TUI** lives at **`scripts/operator/preflight_pyth_tui.py`** (preflight, policy registry, Hermes context). Use that for the terminal operator experience.

Details: **[`seanv3/README.md`](seanv3/README.md)**.

---

This directory holds **SeanV3** and related lab scripts **outside** the main BlackBox Python app tree. **seanv3** (Docker) uses the **Binance** REST path on the host (**WireGuard / Proton** split-tunnel), optional wallet pubkey, **paper-only** behavior, and local **SQLite** + NDJSON.

Optional local **TypeScript** experiments (`superjup.ts`) are separate and not required for the Docker analog.

**Canonical remote host:** **`clawbot.a51.corp`**, repo checkout **`~/blackbox`**. After any doc change, **`git pull origin main`** on the server so paths match this file.

---

## Documentation map

### Primary — Docker container + clawbot

| Doc | What it covers |
|-----|----------------|
| **[`seanv3/README.md`](seanv3/README.md)** | SeanV3 standalone app; **path on clawbot** `~/blackbox/vscode-test/seanv3`; deploy; **`network_mode: host`**; **`capture/`**; backfill |
| **[`../scripts/operator/preflight_pyth_tui.py`](../scripts/operator/preflight_pyth_tui.py)** | **SeanV3 operator TUI** |
| **[`seanv3/SEANV3PY.md`](seanv3/SEANV3PY.md)** | Operator script **`seanv3py`** — deploy / status / logs / stop / restart end-to-end |
| **[`seanv3/TURNOVER_NEXT_STEPS.md`](seanv3/TURNOVER_NEXT_STEPS.md)** | Handoff: `sean_parity.db`, architect mechanical checks, parity command, poller / 451 notes |
| **[`seanv3/docker-compose.yml`](seanv3/docker-compose.yml)** | Service env, volumes, inline comments |

### VPN / routing (required for Binance on the server)

Binance egress uses the **host** routing table (WireGuard **split-tunnel**). The container does **not** run VPN software inside the image.

| Doc / script | What it covers |
|--------------|----------------|
| **[`VPN/README.md`](../VPN/README.md)** | Split-tunnel model, Binance vs production NIC, **HTTP 451** when routing is wrong, `curl` checks |
| **[`scripts/clawbot/binance_api_route_via_proton_wg.sh`](../scripts/clawbot/binance_api_route_via_proton_wg.sh)** | Merge current **`api.binance.com`** IPs into **`wg-proton-mx`** when CDN prefixes drift (run on host, typically with `sudo`) |
| **[`scripts/clawbot/binance_api_knock_then_repair_if_needed.sh`](../scripts/clawbot/binance_api_knock_then_repair_if_needed.sh)** | Lightweight **`/api/v3/ping`** knock; invokes repair script if not HTTP 200 |
| **[`scripts/clawbot/install_binance_wg_route_timer.sh`](../scripts/clawbot/install_binance_wg_route_timer.sh)** | Optional systemd timer for periodic knock + repair |

### Other monorepo paths (not SeanV3 runtime)

Unrelated to SeanV3 Docker/TUI unless you explicitly run a separate compare job. SeanV3 strategy and ledger live under **`seanv3/`** only.

### TypeScript lab (optional; not the Docker image)

These files may exist only on a developer machine unless explicitly committed. They are **not** required for the **`seanv3`** container.

| File | Note |
|------|------|
| `superjup.ts` | Compile-safe stub; not deployed by default |
| `superjup.ts.old` | Legacy reference — **not** SeanV3 runtime |

---

## Fast path — get the container running on the server

```bash
cd ~/blackbox && git pull origin main
cd vscode-test/seanv3
docker compose up -d --build
```

Then read **[`seanv3/README.md`](seanv3/README.md)** first; **[`seanv3/TURNOVER_NEXT_STEPS.md`](seanv3/TURNOVER_NEXT_STEPS.md)** has lab handoff notes.

---

## Related (rest of monorepo)

- **[`docs/architect/local_remote_development_workflow.md`](../docs/architect/local_remote_development_workflow.md)** — local vs clawbot sync
- **[`UIUX.Web/docker-compose.yml`](../UIUX.Web/docker-compose.yml)** — separate web stack (not SeanV3 TUI)
