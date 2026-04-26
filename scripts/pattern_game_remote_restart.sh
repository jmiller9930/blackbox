#!/usr/bin/env bash
# Restart the pattern-game Flask UI on a lab host (used by gsync.py).
# Usage: scripts/pattern_game_remote_restart.sh [REPO_DIR]
# Default REPO_DIR: ~/blackbox

set -euo pipefail
REPO="${1:-$HOME/blackbox}"
REPO="$(cd "$REPO" && pwd)"
cd "$REPO"
export PYTHONPATH="$REPO"
echo "gsync: pattern-game repo HEAD $(git rev-parse --short HEAD 2>/dev/null || echo '?') ($(git log -1 --oneline 2>/dev/null | cut -c1-60 || echo '?'))"

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

# PML runtime layout (directive): never write Flask/proof/batch/telemetry under /tmp.
# Default: ~/blackbox/runtime/ — override with BLACKBOX_PML_RUNTIME_ROOT=/mnt/pml_runtime (or similar).
RUNTIME_ROOT="${BLACKBOX_PML_RUNTIME_ROOT:-$REPO/runtime}"
mkdir -p "$RUNTIME_ROOT/logs" "$RUNTIME_ROOT/proofs" "$RUNTIME_ROOT/batches" "$RUNTIME_ROOT/secrets"
export BLACKBOX_PML_RUNTIME_ROOT="$RUNTIME_ROOT"
export PATTERN_GAME_WEB_LOG_FILE="$RUNTIME_ROOT/logs/pattern_game_web.log"
export PATTERN_GAME_TELEMETRY_DIR="$RUNTIME_ROOT/logs/pattern_game_telemetry"
export PATTERN_GAME_SESSION_LOGS_ROOT="$RUNTIME_ROOT/batches"
# Merge canonical Groundhog bundle into manifests when the file exists (override in shell if needed).
export PATTERN_GAME_GROUNDHOG_BUNDLE="${PATTERN_GAME_GROUNDHOG_BUNDLE:-1}"
echo "gsync: PML runtime root (explicit): $RUNTIME_ROOT (Flask log rotates in-process: max 100MB x 5)"

# ---- OpenAI / GT_DIRECTIVE_026AI: same key contract as external_openai_adapter_v1 and ./scripts/openai_adapter_smoke_v1.sh
# The Flask process must inherit OPENAI so /api/reasoning-model/status matches a successful smoke. Interactive shells
# often have a key; nohup does not read ~/.bashrc. Load, in order: repo .env, optional file override, host secrets, repo runtime secrets.
# See renaissance_v4/game_theory/unified_agent_v1/config/reasoning_router_secrets.local.json.example
if [ -f "$REPO/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO/.env"
  set +a
fi
if [ -n "${BLACKBOX_OPENAI_ENV_FILE:-}" ] && [ -f "${BLACKBOX_OPENAI_ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  . "${BLACKBOX_OPENAI_ENV_FILE}"
  set +a
fi
if [ -f "${HOME}/.blackbox_secrets/openai.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "${HOME}/.blackbox_secrets/openai.env"
  set +a
fi
if [ -f "${RUNTIME_ROOT}/secrets/openai.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "${RUNTIME_ROOT}/secrets/openai.env"
  set +a
fi
# Proof only (value never printed; length 0 = key not in service env — add a file above and restart)
# With set -u, ${#OPENAI_API_KEY} is invalid when unset; use a temp to get length 0.
_OPENAI_KEY_LEN="${OPENAI_API_KEY-}"
echo "gsync: OPENAI_API_KEY set for Flask launch: length ${#_OPENAI_KEY_LEN} (0 = no key file in env chain yet)"
unset _OPENAI_KEY_LEN

# Do not shell-redirect stdout/stderr to /tmp — RotatingFileHandler in web_app consumes logs.
nohup python3 -m renaissance_v4.game_theory.web_app --host 0.0.0.0 --port 8765 </dev/null >/dev/null 2>&1 &
echo "gsync: pattern-game web started (PID $!); log: $PATTERN_GAME_WEB_LOG_FILE"
echo "gsync: open http://$(hostname -f 2>/dev/null || hostname):8765/ (or this host's IP)"
