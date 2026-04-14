# VPN Phase 1 — Binance Split Tunnel Implementation

## 1. Objective

Implement a **production-safe WireGuard split tunnel** on clawbot such that:

- **Binance API traffic → Proton WireGuard (`wg-proton-mx`)**
- **ALL other traffic → normal production network (`ens192`, etc.)**

This must be:
- deterministic  
- testable  
- recoverable  

---

## 2. Non-Negotiable Rules

1. **NO FULL TUNNEL**
   ```
   Forbidden:
   AllowedIPs = 0.0.0.0/0, ::/0
   ```

2. **Binance-only routing**
   - Only `api.binance.com` traffic goes through WireGuard

3. **System stability priority**
   - SSH, dashboards, internal services MUST remain unaffected

4. **Host-level routing**
   - This is NOT container-level VPN
   - Routing decisions happen at kernel level

---

## 3. Architecture Model

```
[Process / Container]
        ↓
   Host Routing Table
        ↓
 ┌───────────────┬─────────────────┐
 │ Binance API   │ Everything else │
 │               │                 │
 ↓               ↓
wg-proton-mx     ens192 (default route)
(Proton VPN)     (normal uplink)
```

---

## 4. Phase 1 Implementation Steps

### Step 1 — Create WireGuard Config (Split Tunnel)

```bash
sudo cat > /etc/wireguard/wg-proton-mx.conf << 'EOF'
[Interface]
PrivateKey = REPLACE_WITH_PRIVATE_KEY
Address = 10.2.0.2/32
DNS = 1.1.1.1

[Peer]
PublicKey = REPLACE_WITH_PROTON_PUBLIC_KEY
Endpoint = REPLACE_WITH_ENDPOINT:51820

# CRITICAL: DO NOT USE 0.0.0.0/0
AllowedIPs = 0.0.0.0/32
PersistentKeepalive = 25
EOF
```

---

### Step 2 — Bring Interface Up

```bash
sudo wg-quick up wg-proton-mx
sudo wg show
```

---

### Step 3 — Route Binance via WireGuard

```bash
cd ~/blackbox
sudo bash scripts/clawbot/binance_api_route_via_proton_wg.sh
```

---

### Step 4 — Install Auto-Repair Timer

```bash
cd ~/blackbox
sudo BLACKBOX_REPO="$HOME/blackbox" ./scripts/clawbot/install_binance_wg_route_timer.sh
```

---

## 5. Validation Checklist

### Internal Connectivity

```bash
curl -s http://localhost
ssh localhost
```

---

### Normal Internet

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://api.github.com/
curl -sS -o /dev/null -w '%{http_code}\n' https://www.google.com/generate_204
```

---

### Binance

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://api.binance.com/api/v3/ping
```

---

### Route Verification

```bash
ip route get $(dig +short api.binance.com | head -n1)
```

---

## 6. Failure + Recovery

### SSH Lost

```bash
sudo wg-quick down wg-proton-mx
```

---

### Binance 451

```bash
sudo bash scripts/clawbot/binance_api_route_via_proton_wg.sh
```

---

### Full Tunnel Applied

```bash
sudo wg-quick down wg-proton-mx
sudo nano /etc/wireguard/wg-proton-mx.conf
```

Remove:
```
AllowedIPs = 0.0.0.0/0
```

---

## 7. Definition of Done

- SSH works with WG enabled  
- Dashboard reachable  
- Non-Binance internet unchanged  
- Binance returns 200  
- Timer auto-repairs routing  

---

## 8. Final Statement

This is not a VPN setup.

This is:

**a controlled routing system that surgically redirects Binance traffic without affecting the rest of the machine**
