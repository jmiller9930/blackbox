# VPN Master Plan — All Phases (Renaissance-Style Network Control)

**System:** Clawbot  
**Authority:** Architect  
**Scope:** Full lifecycle VPN routing system (Binance-specific split tunnel → production-grade network control)

---

# 0. Philosophy

This is NOT a VPN setup.

This is:

> A deterministic traffic control system that routes specific financial endpoints through controlled egress while preserving total system stability.

---

# PHASE 1 — Split Tunnel Foundation

## Objective
- Route Binance → WireGuard
- Everything else → normal network

## Key Rules
- NO full tunnel
- Binance-only routing
- SSH + dashboards must remain stable

## Implementation Summary
- Create wg config (narrow AllowedIPs)
- Bring up interface
- Inject Binance routes
- Install auto-repair timer

## Outcome
- Binance returns 200 (not 451)
- No disruption to system traffic

---

# PHASE 2 — Policy Routing Hardening

## Objective
Prevent routing conflicts and guarantee deterministic behavior

## Additions

### 1. ip rule priority enforcement

```bash
sudo ip rule add to 172.20.0.0/16 lookup main pref 100
sudo ip rule add to 10.0.0.0/8 lookup main pref 100
```

Ensures:
- internal traffic NEVER touches VPN

---

### 2. Binance-specific routing table

Create table:

```bash
echo "200 binance" | sudo tee -a /etc/iproute2/rt_tables
```

Route Binance via WG:

```bash
sudo ip route add default dev wg-proton-mx table binance
sudo ip rule add to $(dig +short api.binance.com | head -n1) table binance
```

---

### 3. Route precedence validation

```bash
ip rule show
ip route show table binance
```

---

## Outcome
- Routing is deterministic
- No accidental leakage into VPN

---

# PHASE 3 — Multi-Endpoint Control

## Objective
Extend beyond Binance without breaking architecture

## Add Controlled Targets
- api.binance.com
- fapi.binance.com
- other approved endpoints

## Controlled Expansion Rule

Each new endpoint must:
- be explicitly listed
- be routable independently
- NOT expand AllowedIPs blindly

---

## Implementation Pattern

```bash
dig +short fapi.binance.com
sudo ip route add <resolved_ip>/32 dev wg-proton-mx
```

---

## Outcome
- Controlled growth
- No accidental full tunnel behavior

---

# PHASE 4 — Monitoring + Telemetry

## Objective
Make routing observable

---

### Add Monitoring Script

```bash
watch -n 5 'ip route | grep wg-proton-mx'
```

---

### Add Health Checks

```bash
curl -s -o /dev/null -w "%{http_code}" https://api.binance.com/api/v3/ping
```

---

### Logging Targets
- route changes
- interface state
- handshake status
- latency

---

## Outcome
- System is observable
- Failures are detectable early

---

# PHASE 5 — Failover + Safety

## Objective
System must fail SAFE, not fail BROKEN

---

### Automatic Fallback Rule

If WG fails:
- traffic must revert to normal network

---

### Watchdog Example

```bash
if ! wg show wg-proton-mx | grep -q "latest handshake"; then
    sudo wg-quick down wg-proton-mx
fi
```

---

### SSH Safety Rule

Always preserve:

```bash
ip rule add from <admin_ip>/32 lookup main pref 50
```

---

## Outcome
- No lockouts
- System self-recovers

---

# PHASE 6 — Production Hardening

## Objective
Make system resilient under real conditions

---

### Add:

- DNS fallback strategy
- multi-endpoint rotation
- rate limiting awareness
- IP drift handling (already partially solved by timer)

---

### Add systemd watchdog

```bash
systemctl enable wg-quick@wg-proton-mx
```

---

## Outcome
- Stable under load
- resilient to API + network changes

---

# PHASE 7 — Final Validation

## Required Tests

### 1. Internal access
- SSH works
- Dashboard loads

### 2. Internet
- GitHub reachable
- Google reachable

### 3. Binance
- returns 200

### 4. Routing

```bash
ip route get $(dig +short api.binance.com | head -n1)
```

Must show:
```
dev wg-proton-mx
```

---

# FINAL SYSTEM DEFINITION

This system is complete when:

- Only Binance uses VPN
- Everything else uses normal network
- Routing is deterministic
- Failures are recoverable
- No full tunnel exists
- System remains stable under all conditions

---

# FINAL STATEMENT

This is not networking.

This is:

> Controlled financial traffic routing with production-grade safeguards

If something breaks:

> routing is wrong — not the application
