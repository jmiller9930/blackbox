#!/usr/bin/env bash
# Sean parity: one-shot Binance klines backfill into capture/sean_parity.db
#
# Clawbot has WireGuard installed; Binance egress uses the split-tunnel WG interface
# (narrow AllowedIPs to Binance API prefixes — see VPN/README.md), not a VPN inside
# the container. This script refuses to hit Binance until the host can reach
# api.binance.com with HTTP 200 — same routing table the container uses (network_mode: host).
#
# Usage (on clawbot, from this directory):
#   ./run-backfill-clawbot.sh
#   LIMIT=1000 ./run-backfill-clawbot.sh
set -euo pipefail
cd "$(dirname "$0")"

PING_URL="${BINANCE_PING_URL:-https://api.binance.com/api/v3/ping}"
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$PING_URL" || echo "000")"
if [[ "$code" != "200" ]]; then
  echo "run-backfill-clawbot: Binance ping ${PING_URL} returned HTTP ${code} (need 200)." >&2
  echo "Fix WireGuard split-tunnel / routes so Binance hits WG (VPN/README.md), then retry." >&2
  exit 1
fi

LIMIT="${LIMIT:-864}"
export LIMIT
docker compose run --rm \
  -e SQLITE_PATH=/capture/sean_parity.db \
  -e LIMIT="${LIMIT}" \
  seanv3 \
  node --experimental-sqlite /app/backfill.mjs
