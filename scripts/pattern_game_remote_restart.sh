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

# ---- OpenAI (external API only): one host file, same as external_openai_secrets_contract_v1 / adapter.
# Optional: repo .env for other vars. Then exactly one of BLACKBOX_OPENAI_ENV_FILE or ~/.blackbox_secrets/openai.env
# (override wins; no duplicate key stores under runtime/ or second copies).
# See: renaissance_v4/game_theory/unified_agent_v1/external_openai_secrets_contract_v1.py
if [ -f "$REPO/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO/.env"
  set +a
fi
O_ENV="${BLACKBOX_OPENAI_ENV_FILE:-$HOME/.blackbox_secrets/openai.env}"
if [ -f "$O_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$O_ENV"
  set +a
fi
# Proof only (value never printed; length 0 = key not in service env — add a file above and restart)
# With set -u, ${#OPENAI_API_KEY} is invalid when unset; use a temp to get length 0.
_OPENAI_KEY_LEN="${OPENAI_API_KEY-}"
echo "gsync: OPENAI_API_KEY set for Flask launch: length ${#_OPENAI_KEY_LEN} (0 = no key file in env chain yet)"
unset _OPENAI_KEY_LEN

# Student behavior probe — default 120s wall clock so slow LLMs can complete ≥1 seal (override per host).
export PATTERN_GAME_STUDENT_PROBE_MAX_WALL_S="${PATTERN_GAME_STUDENT_PROBE_MAX_WALL_S:-120}"

# DeepSeek internal reviewer tier (172.20.2.230 by default): Ask DATA deep route / dual-review reviewer uses this tag.
# Must exist on host — run scripts/verify_deepseek_escalation_ollama_v1.sh after ollama pull.
export DEEPSEEK_ESCALATION_OLLAMA_MODEL="${DEEPSEEK_ESCALATION_OLLAMA_MODEL:-deepseek-r1:14b}"

# Do not shell-redirect stdout/stderr to /tmp — RotatingFileHandler in web_app consumes logs.
nohup python3 -m renaissance_v4.game_theory.web_app --host 0.0.0.0 --port 8765 </dev/null >/dev/null 2>&1 &
echo "gsync: pattern-game web started (PID $!); log: $PATTERN_GAME_WEB_LOG_FILE"
echo "gsync: open http://$(hostname -f 2>/dev/null || hostname):8765/ (or this host's IP)"
