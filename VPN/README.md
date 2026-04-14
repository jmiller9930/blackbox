# VPN profiles (WireGuard)

## CRITICAL — lab requirement (non-negotiable)

**Proton on clawbot is for selective Binance egress only.** It **must not** replace global routing.

| Required | Forbidden |
|----------|-----------|
| Outbound to **Binance-only** destinations via WireGuard | **Full tunnel** (`AllowedIPs = 0.0.0.0/0, ::/0`) |
| Default Internet + internal paths stay on **normal** interfaces / **main** routing table | **Default route override** for the whole system via WG |
| **Internal VPN** (operator → lab) and **trading stack** connectivity remain **stable** and unchanged by default | **System-wide** “all traffic through Proton” |

**Engineering proof** (before calling this done): with WG up, confirm (1) SSH/dashboard from internal path still works, (2) `curl` to **US or other general** public hosts (non-Binance) exits **via the normal uplink** — same behavior as with WG down, (3) Binance-targeted traffic exits via Proton **only** as designed.

The file `Clawbot-MX-FREE-15.full-tunnel.DO-NOT-DEPLOY-ON-CLAWBOT.conf` is a Proton download with **full tunnel** — **do not** deploy it to clawbot **as-is** for production; it violates the requirement above. Use **`wg-proton-binance-only.example.conf`** as a template and narrow **`AllowedIPs`** per operations.

## Scope — host networking (not “Blackbox-only”)

**WireGuard on clawbot is a machine concern.** `wg-proton-mx`, kernel routes, and **`[Peer] AllowedIPs`** (plus any **`/32`** routes merged by ops/scripts) live on the **host**. This is **not** a VPN that exists only inside a Blackbox container.

**Who uses the tunnel:** Anything on that server whose packets **egress the host** toward Binance API destinations that the host routes via **`wg-proton-mx`** — including **other Docker containers** (typical **bridge** networks **NAT to the host**; the **host** then chooses the route by destination), **other users’ processes**, and **systemd services** — **if** they resolve the same Binance endpoints and you have **not** built a separate routing table or VPN **only** inside some other container. There is no requirement that only Blackbox code may use Proton for Binance on this host.

**What is Blackbox-specific in *this* repo:** the **documentation** (this file), **maintenance scripts** under **`scripts/clawbot/`** (e.g. **`binance_api_route_via_proton_wg.sh`**), and **Docker Compose** choices (**`network_mode: host`** for our services in **`UIUX.Web/`**, **`vscode-test/seanv3/`**, etc.) so **our** stacks use the **normal host forwarding path** and the same routing table as the rest of the machine. The **tunnel interface itself** is **host infrastructure**, not a feature shipped only inside a Blackbox image.

## Traffic model (authoritative) — Binance via Proton WG vs production network

This section states **exactly** what must happen on **clawbot** so engineering, operators, and audits align. It is not optional interpretation.

### Binance traffic — **must** use `wg-proton-mx` (Proton WireGuard)

**Definition:** Any **outbound** traffic from clawbot whose **destination** is **Binance public API** (including Blackbox market OHLC / connectivity checks, and **any other process on the host** that hits the same API hosts). Today that is primarily:

- **HTTPS** to **`api.binance.com`** (REST: ping, klines, and any path callers use under that host — Jupiter V3 / Sean parity, sync jobs, ad-hoc `curl`, etc.).

**Requirement:** That traffic **must** leave the host through the **Proton WireGuard** interface **`wg-proton-mx`**, using the Proton exit so Binance applies **eligible** jurisdiction checks (symptom when wrong: **HTTP 451** if packets exit the **production** NIC instead).

**Mechanism:** Linux sends those packets to **`wg-proton-mx`** only when:

1. **`[Peer] AllowedIPs`** on the WireGuard config includes the **current** destination prefixes for Binance API (CDN IPs **change** — see `scripts/clawbot/binance_api_route_via_proton_wg.sh`), and  
2. Host routes (e.g. **`/32`** via **`dev wg-proton-mx`**) match those destinations, and  
3. Application processes that call Binance use the **host routing table** (e.g. **`network_mode: host`** on the relevant Docker services — see `UIUX.Web/docker-compose.yml` and `vscode-test/seanv3/docker-compose.yml`). The **Sean V3** parity container (**`seanv3`**) **must** keep **`network_mode: host`**; do not run it on the default bridge for production Binance traffic (see **`vscode-test/seanv3/README.md`** — VPN rules table).

**Not in scope for “Binance via Proton”:** Trading venues other than Binance, wallet RPC, Solana JSON-RPC, Pyth/Hermes, Slack, Git, or generic web — those are **not** Binance API traffic and **must not** be forced through this tunnel unless a **separate** directive says so.

### Local and production network traffic — **must** use the normal production path

**Definition:** Everything that is **not** Binance public API traffic as above, including:

- **Same LAN / corporate / lab network:** SSH administration, internal IPs, monitoring, mounts, internal DNS, traffic between Docker and host where the **destination** is not Binance API.  
- **General Internet (non-Binance):** Package installs, Git, Docker registry pulls, Slack/webhooks, public health checks, arbitrary `curl` to non-Binance hosts — **egress via the normal production uplink** (on clawbot typically the default route via **`ens192`** and gateway **`172.20.2.1`**, per live routing).  
- **Operator-facing services** listening on clawbot (HTTPS dashboard, nginx): **inbound** sessions; return traffic follows normal forwarding unless the **server-initiated** leg is to Binance (then Binance rules above apply).

**Requirement:** This traffic **must not** be dragged into a **full-tunnel** Proton profile. It uses the **main** routing table and **production** interface(s) so SSH, dashboards, and day-to-day operations stay stable — the same outcome as “no VPN for general use,” with **only** Binance API steered to Proton.

### Summary table

| Traffic class | Egress path | Interface / policy |
|---------------|-------------|-------------------|
| Binance public API (e.g. `api.binance.com`) | **Proton WireGuard** | `wg-proton-mx`, narrow `AllowedIPs` + maintained routes |
| Local LAN, internal, and all other Internet | **Production network** | Default route / `ens192` (normal uplink), **not** full-tunnel WG |

### US-based and general Internet destinations (must stay reachable)

**Split tunneling is not “Binance only” vs “internal only.”** Anything that is **not** listed in WireGuard **`AllowedIPs`** uses the **main** routing table and your **normal** ISP/LAN path — including:

- **US-hosted** APIs, websites, CDNs, DNS, package mirrors, Git hosts, Slack/webhooks, etc.
- **Any country’s** public endpoints, as long as they are **not** routed through the narrow Binance prefixes.

So you **do** get normal access to US IPs and URLs **as long as** you **do not** use a full tunnel and **do not** put huge swaths of the Internet (e.g. `0.0.0.0/0`) in **`AllowedIPs`**. If a destination must **not** use Proton, it simply must **not** be covered by the peer’s **`AllowedIPs`** (or must be overridden with higher-priority **`ip rule`** to `main` if you add custom policy routing).

**Quick check from clawbot** (after WG is up, Binance-only config):

```bash
# Should succeed via normal path — pick any stable US endpoint you care about
curl -sS -o /dev/null -w '%{http_code}\n' https://www.google.com/generate_204
curl -sS -o /dev/null -w '%{http_code}\n' https://api.github.com/
# Binance API — must return 200 when split-tunnel routing to Binance is correct (not 451)
curl -sS -o /dev/null -w '%{http_code}\n' https://api.binance.com/api/v3/ping
```

Sean parity klines backfill (preflights the Binance ping, then `docker compose run`): `vscode-test/seanv3/run-backfill-clawbot.sh`.

If those fail or hang while Binance-only WG is up, routing is wrong (too-wide **`AllowedIPs`** or conflicting **`ip rule`**).

### Binance API must use Proton — operational rule

**Intent:** Only **Binance REST** (and whatever narrow peers ops require) uses **`wg-proton-mx`**. **Everything else** uses the normal uplink (`ens192`, etc.). That is the split-tunnel contract above.

**Why 451 happens with WG still “up”:** `api.binance.com` resolves to **CDN IPs that change**. If **`[Peer] AllowedIPs`** only lists the **VPN server** (e.g. one `/32`) and **not** the **current** Binance API addresses, the kernel routes Binance to **`ens192`** → Binance returns **451**. The tunnel is up; **Binance traffic was never selected for it.**

**Fix on clawbot (root):** run the repo script whenever DNS/CDN drifts or after reboot — it merges **`api.binance.com`** A records into the peer **`allowed-ips`** and installs **`/32`** routes via **`wg-proton-mx`**, then checks ping **200**:

```bash
cd ~/blackbox
sudo bash scripts/clawbot/binance_api_route_via_proton_wg.sh
```

**Automatic refresh (recommended):** install the systemd timer on clawbot. **Every 1 minute** it runs a **lightweight knock**: a single **`GET /api/v3/ping`** to Binance (minimal load — not a klines barrage). If HTTP **200**, it stops there. If **not** (e.g. **451**, CDN drift), it runs **`binance_api_route_via_proton_wg.sh`** to merge current **`api.binance.com`** IPs into **`wg-proton-mx`** and fix routes. First run **~45s after boot**.

```bash
cd ~/blackbox && git pull origin main
sudo BLACKBOX_REPO="$HOME/blackbox" ./scripts/clawbot/install_binance_wg_route_timer.sh
```

Units live in `scripts/clawbot/systemd/` (`binance-wg-route.service` + `binance-wg-route.timer`). Knock entrypoint: `scripts/clawbot/binance_api_knock_then_repair_if_needed.sh`. Check: `systemctl list-timers binance-wg-route.timer`, `journalctl -u binance-wg-route.service -n 50`.

Persist **`AllowedIPs`** in `/etc/wireguard/wg-proton-mx.conf` when you have a stable workflow; Proton may still overwrite runtime **`wg set`** — the timer re-applies on the next interval.

## Files

- `Clawbot-MX-FREE-15.full-tunnel.DO-NOT-DEPLOY-ON-CLAWBOT.conf` — historical Proton profile (**full tunnel — not compliant** with lab selective-routing requirement; reference keys/peer only when building a split config).
- `wg-proton-binance-only.example.conf` — **template** for Binance-only routing (replace keys, endpoint, **`AllowedIPs`** with maintained Binance prefixes).

## Security

These files contain **private keys**. Do **not** publish the repo or share configs publicly. Rotate the key in Proton if a file was ever exposed.

## Headless server warning

Configs with `AllowedIPs = 0.0.0.0/0, ::/0` send **all** traffic (including SSH return paths / DNS) through the tunnel. On a server whose primary NIC is **not** fully managed by NetworkManager, bringing the tunnel up can **drop SSH** or stall `wg-quick`.

**Prefer:** out-of-band / iDRAC / hypervisor console, or test only from a **local console** session.

### Recovery (if SSH is lost)

1. Log in via **hypervisor / serial / physical console**.
2. Tear down the interface:
   ```bash
   sudo wg-quick down wg-proton-mx
   ```
3. If the unit was enabled:
   ```bash
   sudo systemctl disable wg-quick@wg-proton-mx 2>/dev/null
   ```
4. Restore DNS if needed (e.g. `resolv.conf`).

## Install on Debian (clawbot-style)

```bash
sudo apt install wireguard-tools openresolv
# Install a SPLIT config only — e.g. after copying and editing wg-proton-binance-only.example.conf:
sudo install -m 600 -o root -g root wg-proton-binance-only.example.conf /etc/wireguard/wg-proton-mx.conf
# Never install Clawbot-MX-FREE-15.full-tunnel.DO-NOT-DEPLOY-ON-CLAWBOT.conf as production wg-proton-mx.conf.
```

**Do not** run `wg-quick up` over SSH unless you accept lockout risk.

### Optional: systemd

After manual testing from console:

```bash
sudo systemctl enable wg-quick@wg-proton-mx
sudo systemctl start wg-quick@wg-proton-mx
```

## Target architecture (internal admin vs Binance egress)

Canonical detail: the **Traffic model (authoritative)** section at the top of this file (Binance via Proton WG vs production network).

Intended data path:

```text
YOU (internal VPN)
   ↓
clawbot
   ↓
[route decision]
   ├── internal network → normal interface (LAN / corporate path)
   └── Binance (API)    → Proton WireGuard interface (exit IP outside US if required)
```

**Meaning**

- **Management / internal:** SSH, dashboards, corp subnets — must **not** default into the Proton full tunnel or you risk lockout or broken return paths.
- **Binance only:** Only traffic to Binance endpoints should use the WireGuard interface and Proton exit.

### How Linux implements this

1. **WireGuard `[Peer] AllowedIPs` (on this host)**  
   This controls which **destination prefixes** are routed **through the peer**.  
   - **Avoid on servers:** `AllowedIPs = 0.0.0.0/0, ::/0` (full tunnel — includes SSH, DNS, internal).  
   - **Toward your goal:** set `AllowedIPs` to **only** the IPv4/v6 prefixes used by the Binance APIs you need (see below). Other traffic stays on the **main** table → normal NIC.

2. **Binance IP reality**  
   Names like `api.binance.com` are often behind CDNs; IPs **move**. Typical approaches: periodic **resolve + update** routes/`AllowedIPs`, or a maintained list of CIDRs if governance allows — both need ops ownership.

3. **Protect internal paths first**  
   Use **`ip rule`** so traffic **to** your internal / corp / VPN-client subnets always **`lookup main`** (or the table that has the correct interface for “YOU → clawbot”) with **higher priority** (lower `pref` number) than any WireGuard policy rules.

4. **DNS**  
   Global `DNS =` under `[Interface]` may be wrong if only Binance should use the tunnel; tune once L3 routing is correct.

### Proton app vs raw WireGuard

The Proton **CLI/GUI** integrates with **NetworkManager** and app split tunneling. On a host where the uplink is **not** NM-managed, **manual WireGuard** plus **narrow `AllowedIPs`** plus **`ip rule`** for internal ranges is often clearer — but **you** maintain Binance destinations and rule order.

## Root cause — SSH / HTTPS outage (2026-04, resolved)

**What failed:** Timeouts to `172.20.2.161:443`, `:80`, and SSH; external front door also appeared down.

**Actual cause:** WireGuard was brought up with the **full-tunnel** Proton profile (now named **`Clawbot-MX-FREE-15.full-tunnel.DO-NOT-DEPLOY-ON-CLAWBOT.conf`**), whose **`[Peer] AllowedIPs`** is **`0.0.0.0/0, ::/0`** (full tunnel). **`wg-quick`** then installed **policy routing** (`ip rule` → table **51820**), **fwmark** rules, and **nft** hooks so **all** IPv4/v6 traffic was steered through **`wg-proton-mx`**. That is incompatible with a **lab server** that must keep **management** (SSH), **Docker/nginx**, and **internal** paths on the normal uplink. Return paths, DNS (`resolvconf`), and listener reachability were effectively broken for normal access.

**Recovery:** `sudo wg-quick down wg-proton-mx` (exit 0) removed the rules, deleted the interface, and cleared **`resolvconf`** / **nft** side effects; `sudo wg show` empty confirmed no active tunnel. SSH and services could work again.

**Prevention:** Never deploy that profile **as-is** on clawbot. Use **Binance-only `AllowedIPs`** (and internal **`ip rule`** precedence) per sections above.

## Dependencies

- `openresolv` (or another `resolvconf` provider) is required if the config has `DNS = …` lines, or `wg-quick` will fail at `resolvconf: command not found`.
