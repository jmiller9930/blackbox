#!/usr/bin/env bash
# Restart the pattern-game Flask UI on a lab host (used by gsync.py).
# Usage: scripts/pattern_game_remote_restart.sh [REPO_DIR]
# Default REPO_DIR: ~/blackbox

set -euo pipefail
REPO="${1:-$HOME/blackbox}"
REPO="$(cd "$REPO" && pwd)"
cd "$REPO"
export PYTHONPATH="$REPO"

if [ -f "$REPO/.venv_pattern_game/bin/activate" ]; then
  # shellcheck source=/dev/null
  source "$REPO/.venv_pattern_game/bin/activate"
fi

echo "gsync: pattern-game web — release port 8765 (if in use)…"
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8765/tcp 2>/dev/null || true
else
  pkill -f 'renaissance_v4\.game_theory\.web_app' 2>/dev/null || true
fi
sleep 1

LOG="${TMPDIR:-/tmp}/pattern_game_web.log"
nohup python3 -m renaissance_v4.game_theory.web_app --host 0.0.0.0 --port 8765 >>"$LOG" 2>&1 &
echo "gsync: pattern-game web started (PID $!); log: $LOG"
echo "gsync: open http://$(hostname -f 2>/dev/null || hostname):8765/ (or this host's IP)"
