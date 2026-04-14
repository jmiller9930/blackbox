#!/usr/bin/env bash
# Clawbot: lightweight knock only — do NOT spam Binance or churn WireGuard on every tick.
#
# Contract: one GET to /api/v3/ping. HTTP 200 => exit immediately (no wg set, no routes, no dig).
# Only if ping is not 200 => run binance_api_route_via_proton_wg.sh (recover).
#
# Systemd timer invokes this ~every minute; happy path is a single tiny request.
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
