# vscode-test — lab / parity (Blackbox)

## What this is for (parity check)

**Goal:** Use this tree as a **parity check** on **Blackbox**. Sean V3 and Blackbox are **separate running systems** (there is no live wire between them). The point is to show they **behave the same** when they should:

- **Same strategy** — Jupiter / Sean V3 policy as implemented in Blackbox (`jupiter_3_sean_policy.py`, baseline bridge, dashboard) should match the **intent** of Sean V3.
- **Same market API path** — Binance OHLC used for that lane should come from the **same** REST/split-tunnel setup so bars match (`binance_strategy_bars_5m` vs `sean_parity.db` / ingest checks).

**Success looks like:**  
If **Sean V3 would take a trade** on a bar (signal says enter / side / sizing narrative), **Blackbox should show an equivalent trade** (or permitted execution path) for that policy lane. If **Sean V3 would take no trade**, **Blackbox should show no trade** for that lane on the same bar. **Flat on both sides** when the strategy says flat is the normal “in sync” outcome.

**How you verify:** Compare captured Sean-side SQLite + Blackbox market DB + ledger/policy rows (e.g. `jup_v3_parity_compare`, dashboard/ledger audits) — not by assuming one process calls the other.

---

This directory holds **standalone** tooling **outside** the main Python app: **seanv3** (Docker) uses the same **Binance financial REST** path (host **WireGuard / Proton** split-tunnel), optional **wallet identity** (pubkey only), **paper-only** signals (no on-chain execution), and **onboard SQLite** for polls + analog events. **Authoritative Sean V3 policy math** remains in Python (`jupiter_3_sean_policy.py`); the container supports **ingest logging** and comparison.

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
