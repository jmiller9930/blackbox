#!/usr/bin/env bash
# Exec target for tmux / systemd: load repo .env then run Karpathy loop-daemon.
# Same Ollama resolution as messaging path (OLLAMA_BASE_URL from .env).
set -euo pipefail
REPO="${BLACKBOX_REPO:-${HOME}/blackbox}"
cd "$REPO"
# shellcheck disable=SC1091
source "${REPO}/scripts/anna_karpathy_loop_env.inc.sh"
_load_karpathy_loop_env "$REPO"
export PYTHONPATH="${REPO}/scripts/runtime:${REPO}${PYTHONPATH:+:${PYTHONPATH}}"
PY="${REPO}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi
exec "$PY" "${REPO}/scripts/runtime/anna_training_cli.py" loop-daemon "$@"
