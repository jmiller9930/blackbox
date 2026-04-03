#!/usr/bin/env bash
# Launch Anna training from the lab host (e.g. clawbot ~/blackbox).
#
# Usage (on server, repo root = default ~/blackbox):
#   ./scripts/anna_training_launch_server.sh
#   ./scripts/anna_training_launch_server.sh --once          # non-interactive: one dashboard then exit
#   RECORD_MARKET_SNAPSHOT=1 ./scripts/anna_training_launch_server.sh --once
#
# Env:
#   BLACKBOX_REPO          — repo path (default: $HOME/blackbox)
#   RECORD_MARKET_SNAPSHOT — if 1, run one Pyth+Coinbase(+Jupiter) snapshot into data/sqlite/market_data.db first
#   MARKET_DATA_SKIP_JUPITER — if 1, passed implicitly not set here; export before run if needed
#
set -euo pipefail

REPO="${BLACKBOX_REPO:-${HOME}/blackbox}"
cd "${REPO}"

export PYTHONPATH="${REPO}/scripts/runtime:${REPO}${PYTHONPATH:+:${PYTHONPATH}}"

if [[ "${RECORD_MARKET_SNAPSHOT:-0}" == "1" ]]; then
  echo "=== Recording one market_data snapshot (preflight) ===" >&2
  python3 -m market_data
fi

echo "=== Anna training: school (readiness + gates + start) ===" >&2
exec python3 scripts/runtime/anna_go_to_school.py "$@"
