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
#   BLACKBOX_KARPATHY_LOOP_ENABLED=1 — required for long-running loop (opt-in; see anna_karpathy_loop_daemon.py)
#
# Loads repo .env / .env.local via scripts/anna_karpathy_loop_run.sh so OLLAMA_BASE_URL
# and BLACKBOX_JACK_EXECUTOR_CMD match the rest of Anna (see scripts/runtime/_ollama.py).
#
set -euo pipefail

REPO="${BLACKBOX_REPO:-${HOME}/blackbox}"
SESSION="${ANNA_TMUX_SESSION:-anna-karpathy-loop}"
cd "${REPO}"

RUNNER="${REPO}/scripts/anna_karpathy_loop_run.sh"
if [[ ! -x "$RUNNER" ]]; then
  chmod +x "$RUNNER" 2>/dev/null || true
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found. Install tmux or run loop-daemon under screen/systemd." >&2
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running. Attach: tmux attach -t $SESSION" >&2
  exit 1
fi

# Detached session: loop runs until SIGTERM; survives SSH logout.
tmux new-session -d -s "$SESSION" "$(printf '%q' "$RUNNER")"

echo "Started Karpathy loop-daemon in tmux session: $SESSION"
echo "  Attach: tmux attach -t $SESSION"
echo "  Stop:   tmux kill-session -t $SESSION   (or attach and Ctrl+C)"
