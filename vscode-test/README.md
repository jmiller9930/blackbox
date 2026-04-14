# vscode-test — lab / SeanV3 + parity vs BlackBox

## What this is for

**BlackBox is one trade system. SeanV3 is another.** This tree hosts **SeanV3** as it grows into a **standalone paper engine** (own data, decisions, lifecycle, ledger, reporting). **Comparison** to BlackBox is a **separate layer** that only gives clean answers once SeanV3 can stand on its own — see **[`seanv3/README.md`](seanv3/README.md)** (architectural principle + gap table).

**Parity goal (after both systems are complete enough):** On the same Binance bar identity (`market_event_id` / candle open) and the same strategy intent, **SeanV3 outcomes** and **BlackBox outcomes** should be **diffable** without conflating “harness bug” with “strategy bug.”

**How you verify (when wired):** SeanV3 ledger + reports vs BlackBox market DB / policy / ledger artifacts (e.g. `jup_v3_parity_compare`) — **not** by assuming one process calls the other.

---

This directory holds **standalone** tooling **outside** the main Python app: **seanv3** (Docker) uses the **Binance financial REST** path on the host (**WireGuard / Proton** split-tunnel), optional **wallet identity** (pubkey only), **paper-only** chain behavior, and local **SQLite** + NDJSON. Today’s container is **strong on ingest**; **evaluation + lifecycle + trade ledger** are **engineering backlog** per [`seanv3/README.md`](seanv3/README.md). BlackBox’s `jupiter_3_sean_policy.py` remains the **BlackBox** implementation of the strategy spec until SeanV3 runs its own evaluator in-process.

Optional local **TypeScript** experiments (`superjup.ts`) are separate and not required for the Docker analog.

**Canonical remote host:** **`clawbot.a51.corp`**, repo checkout **`~/blackbox`**. After any doc change, **`git pull origin main`** on the server so paths match this file.

---

## Documentation map

### Primary — Docker container + clawbot

| Doc | What it covers |
|-----|----------------|
| **[`seanv3/README.md`](seanv3/README.md)** | What the image is; **path on clawbot** `~/blackbox/vscode-test/seanv3`; **deploy** (`git pull`, `docker compose up -d --build`); **`network_mode: host`**; logs; **`capture/`** (NDJSON + SQLite); **`run-backfill-clawbot.sh`**; **`jup_v3_parity_compare`** command |
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

### Python — Sean V3 policy vs parity tooling (main repo)

| Area | Path |
|------|------|
| Jupiter_3 policy | [`modules/anna_training/jupiter_3_sean_policy.py`](../modules/anna_training/jupiter_3_sean_policy.py) |
| Baseline adapter (`evaluate_sean_jupiter_baseline_v3`) | [`modules/anna_training/sean_jupiter_baseline_signal.py`](../modules/anna_training/sean_jupiter_baseline_signal.py) |
| Sean SQLite ↔ Blackbox compare | [`modules/anna_training/jup_v3_parity_compare.py`](../modules/anna_training/jup_v3_parity_compare.py) |

### TypeScript lab (optional; not the Docker image)

These files may exist only on a developer machine unless explicitly committed. They are **not** required for the **`seanv3`** container.

| File | Note |
|------|------|
| `superjup.ts` | Compile-safe stub; not deployed by default |
| `superjup.ts.old` | Legacy reference bot — **do not** use for current parity proof; Python + `seanv3` are authoritative |

---

## Fast path — get the container running on the server

```bash
cd ~/blackbox && git pull origin main
cd vscode-test/seanv3
docker compose up -d --build
```

Then read **[`seanv3/README.md`](seanv3/README.md)** first; use **[`seanv3/TURNOVER_NEXT_STEPS.md`](seanv3/TURNOVER_NEXT_STEPS.md)** for acceptance / parity follow-ups.

---

## Related Blackbox docs

- **[`docs/architect/local_remote_development_workflow.md`](../docs/architect/local_remote_development_workflow.md)** — local vs clawbot sync
- **[`UIUX.Web/docker-compose.yml`](../UIUX.Web/docker-compose.yml)** — dashboard stack; some services use host network for the same Binance routing reason (see comments there)
