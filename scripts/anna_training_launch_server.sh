#!/usr/bin/env bash
# Single Anna training entry for the lab host (e.g. clawbot ~/blackbox):
#   (optional) market snapshot → school (enroll + Karpathy method) → long-running Karpathy loop daemon.
#
# School assigns curriculum/method; the daemon is the same Karpathy *loop* in continuous form
# (heartbeats, iteration, grade-12 snapshots). Learning over time assumes the daemon stays up
# (screen/tmux/systemd) unless you only run a one-off.
#
# Usage:
#   ./scripts/anna_training_launch_server.sh --once
#   RECORD_MARKET_SNAPSHOT=1 ./scripts/anna_training_launch_server.sh --once
#
# After `school --once`, the script starts `anna_karpathy_loop_daemon.py` by default (same shell
# replaced with exec). To run school only (no daemon): ANNA_TRAINING_LAUNCH_DAEMON=0
# To chain daemon after interactive school too: ANNA_TRAINING_ALWAYS_DAEMON=1 ./scripts/anna_training_launch_server.sh
#
# Env:
#   BLACKBOX_REPO — repo path (default: $HOME/blackbox)
#   RECORD_MARKET_SNAPSHOT — if 1, run one market_data snapshot first
#   MARKET_DATA_SKIP_JUPITER — if 1, snapshot uses --no-jupiter
#   ANNA_TRAINING_LAUNCH_DAEMON — if 0/false, run school only (no long-running loop after)
#   ANNA_TRAINING_ALWAYS_DAEMON — if 1, start daemon even after interactive school (no --once)
#   ANNA_LOOP_INTERVAL_SEC — daemon tick interval (default 5)
#
set -euo pipefail

REPO="${BLACKBOX_REPO:-${HOME}/blackbox}"
cd "${REPO}"

export PYTHONPATH="${REPO}/scripts/runtime:${REPO}${PYTHONPATH:+:${PYTHONPATH}}"

if [[ "${RECORD_MARKET_SNAPSHOT:-0}" == "1" ]]; then
  echo "=== Recording one market_data snapshot (preflight) ===" >&2
  MD_EXTRA=()
  case "${MARKET_DATA_SKIP_JUPITER:-}" in
    1|true|yes|on) MD_EXTRA+=(--no-jupiter) ;;
  esac
  python3 -m market_data "${MD_EXTRA[@]}"
fi

echo "=== Anna training: school (readiness + gates + start) ===" >&2
python3 scripts/runtime/anna_go_to_school.py "$@"
rc=$?

_launch_daemon() {
  case "${ANNA_TRAINING_LAUNCH_DAEMON:-1}" in
    0|false|no|off) return 0 ;;
  esac
  echo "=== Karpathy learning loop (long-running; same method as school; Ctrl+C or SIGTERM to stop) ===" >&2
  exec python3 scripts/runtime/anna_karpathy_loop_daemon.py
}

_has_once=0
_has_always=0
for a in "$@"; do
  [[ "$a" == "--once" ]] && _has_once=1
done
case "${ANNA_TRAINING_ALWAYS_DAEMON:-0}" in
  1|true|yes|on) _has_always=1 ;;
esac

if [[ "$rc" -ne 0 ]]; then
  exit "$rc"
fi

if [[ "$_has_once" -eq 1 ]] || [[ "$_has_always" -eq 1 ]]; then
  _launch_daemon
fi

exit "$rc"
