#!/usr/bin/env bash
# Clawbot: route Binance REST (api.binance.com) through existing Proton WireGuard (wg-proton-mx).
#
# Symptom: curl https://api.binance.com/api/v3/ping returns 451 while WG is "up" — traffic was
# still exiting ens192 because Binance CDN IPs were not in [Peer] AllowedIPs / host routes.
#
# Run on the host (needs root): sudo ./binance_api_route_via_proton_wg.sh
# Automatic (recommended on clawbot): timer calls binance_api_knock_then_repair_if_needed.sh every 1 min; this script runs only when ping != 200.
#
# Does NOT enable full-tunnel; only merges current api.binance.com A records into the peer
# allowed-ips and installs /32 routes via wg-proton-mx.
set -euo pipefail

WG_IF="${WG_IF:-wg-proton-mx}"
BINANCE_HOST="${BINANCE_HOST:-api.binance.com}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! ip link show "$WG_IF" &>/dev/null; then
  echo "Interface $WG_IF not found." >&2
  exit 1
fi

PEER_KEY="$(wg show "$WG_IF" peers | head -1)"
if [[ -z "${PEER_KEY}" ]]; then
  echo "No peer on $WG_IF." >&2
  exit 1
fi

# Existing allowed prefixes for this peer (space-separated CIDRs)
EXISTING=()
while read -r c; do
  [[ -n "$c" ]] && EXISTING+=("$c")
done < <(wg show "$WG_IF" allowed-ips | awk -v k="$PEER_KEY" '$1 == k { for (i = 2; i <= NF; i++) print $i }')

# Current Binance API A records (IPv4)
API_IPS=()
while read -r ip; do
  [[ -n "$ip" ]] && API_IPS+=("$ip")
done < <(getent ahosts "$BINANCE_HOST" 2>/dev/null | awk '/STREAM/ {print $1}' | sort -u)
if [[ ${#API_IPS[@]} -eq 0 ]]; then
  while read -r ip; do
    [[ -n "$ip" ]] && API_IPS+=("$ip")
  done < <(dig +short "$BINANCE_HOST" A 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | sort -u)
fi
if [[ ${#API_IPS[@]} -eq 0 ]]; then
  echo "Could not resolve $BINANCE_HOST" >&2
  exit 1
fi

MERGED=("${EXISTING[@]}")
for ip in "${API_IPS[@]}"; do
  cidr="${ip}/32"
  found=0
  for e in "${EXISTING[@]}"; do
    if [[ "$e" == "$cidr" ]]; then
      found=1
      break
    fi
  done
  if [[ "$found" -eq 0 ]]; then
    MERGED+=("$cidr")
  fi
done

ALLOWED="$(IFS=','; echo "${MERGED[*]}")"
wg set "$WG_IF" peer "$PEER_KEY" allowed-ips "$ALLOWED"

for ip in "${API_IPS[@]}"; do
  ip route replace "${ip}/32" dev "$WG_IF"
done

echo "wg-proton-mx peer allowed-ips: $ALLOWED"
echo "Routes via ${WG_IF}: $(printf '%s ' "${API_IPS[@]}")"
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "https://${BINANCE_HOST}/api/v3/ping" || echo "000")"
echo "Binance ping HTTP: $code (want 200)"
[[ "$code" == "200" ]]
