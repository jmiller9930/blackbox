#!/usr/bin/env bash
# Sean parity: one-shot Binance klines backfill into capture/sean_parity.db
#
# Binance egress on clawbot must use the Proton split-tunnel / WireGuard path
# (see VPN/README.md). This script refuses to hit Binance until the host can
# reach api.binance.com with HTTP 200 — i.e. the same routing table the container
# uses (network_mode: host).
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
  echo "Bring up Proton/WireGuard Binance egress on this host (VPN/README.md), then retry." >&2
  exit 1
fi

LIMIT="${LIMIT:-864}"
export LIMIT
docker compose run --rm \
  -e SQLITE_PATH=/capture/sean_parity.db \
  -e LIMIT="${LIMIT}" \
  binance-klines \
  node --experimental-sqlite /app/backfill.mjs
