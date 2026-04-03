#!/usr/bin/env bash
# Run the Karpathy learning-loop daemon on the lab host (e.g. clawbot ~/blackbox).
# Stops on SIGTERM/SIGINT — use systemd Type=simple, or screen/tmux.
#
# Usage:
#   ./scripts/anna_karpathy_loop_server.sh
#   ANNA_LOOP_INTERVAL_SEC=600 ./scripts/anna_karpathy_loop_server.sh
#   RECORD_MARKET_SNAPSHOT_EACH_TICK=1 MARKET_DATA_SKIP_JUPITER=1 ./scripts/anna_karpathy_loop_server.sh
#
set -euo pipefail
REPO="${BLACKBOX_REPO:-${HOME}/blackbox}"
cd "${REPO}"
# shellcheck disable=SC1091
source "${REPO}/scripts/anna_karpathy_loop_env.inc.sh"
_load_karpathy_loop_env "$REPO"
export PYTHONPATH="${REPO}/scripts/runtime:${REPO}${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 scripts/runtime/anna_karpathy_loop_daemon.py "$@"
