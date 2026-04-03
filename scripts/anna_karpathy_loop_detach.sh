#!/usr/bin/env bash
# ONE command: start Karpathy loop-daemon in a detached tmux session (survives SSH disconnect).
#
# Usage (repo root, e.g. clawbot ~/blackbox):
#   ./scripts/anna_karpathy_loop_detach.sh
#
# Then (optional): tmux attach -t anna-karpathy-loop
# Stop: attach and Ctrl+C, or: tmux kill-session -t anna-karpathy-loop
#
# Env:
#   BLACKBOX_REPO — default ~/blackbox
#   ANNA_TMUX_SESSION — tmux name (default anna-karpathy-loop)
#   ANNA_LOOP_INTERVAL_SEC — passed through (daemon default 5)
#
set -euo pipefail

REPO="${BLACKBOX_REPO:-${HOME}/blackbox}"
SESSION="${ANNA_TMUX_SESSION:-anna-karpathy-loop}"
cd "${REPO}"

PY="${REPO}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found. Install tmux or run loop-daemon under screen/systemd." >&2
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running. Attach: tmux attach -t $SESSION" >&2
  exit 1
fi

export PYTHONPATH="${REPO}/scripts/runtime:${REPO}${PYTHONPATH:+:${PYTHONPATH}}"

# Detached session: loop runs until SIGTERM; survives SSH logout.
tmux new-session -d -s "$SESSION" \
  "cd $(printf '%q' "$REPO") && export PYTHONPATH=$(printf '%q' "$PYTHONPATH") && exec $(printf '%q' "$PY") $(printf '%q' "$REPO/scripts/runtime/anna_training_cli.py") loop-daemon"

echo "Started Karpathy loop-daemon in tmux session: $SESSION"
echo "  Attach: tmux attach -t $SESSION"
echo "  Stop:   tmux kill-session -t $SESSION   (or attach and Ctrl+C)"
