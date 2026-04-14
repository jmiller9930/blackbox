#!/usr/bin/env bash
# Clawbot: 1-minute "knock" — single lightweight GET to Binance /api/v3/ping.
# If HTTP 200, exit (no WireGuard churn, minimal API load). If not, run full route repair.
#
# Intended for systemd timer every 1 minute — keepalive without hammering Binance.
set -euo pipefail

BINANCE_HOST="${BINANCE_HOST:-api.binance.com}"
REPAIR="$(cd "$(dirname "$0")" && pwd)/binance_api_route_via_proton_wg.sh"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 "https://${BINANCE_HOST}/api/v3/ping" 2>/dev/null || echo "000")"
if [[ "$code" == "200" ]]; then
  echo "binance knock: OK (HTTP 200) — no repair"
  exit 0
fi

echo "binance knock: HTTP ${code} — running WG route repair"
exec /bin/bash "$REPAIR"
