#!/usr/bin/env sh
# Proves: smoke OK, key present in *this* process without echoing the value, and
# GET /api/reasoning-model/status reports openai key diagnostics. Run on the same host/user as
# Pattern Machine Flask, from repo root (e.g. clawbot after gsync + restart):
#   ./scripts/verify_pattern_game_openai_v1.sh
# Optional: PATTERN_GAME_STATUS_URL (default http://127.0.0.1:8765/api/reasoning-model/status)
set -e
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=.
U="${PATTERN_GAME_STATUS_URL:-http://127.0.0.1:8765/api/reasoning-model/status}"
echo "== 0) Canonical external API env file (single source; same as adapter) =="
python3 -c "from renaissance_v4.game_theory.unified_agent_v1.external_openai_secrets_contract_v1 import resolved_external_openai_env_file_v1 as p; print(p())"
echo "== 1) This shell: OPENAI_API_KEY length (value not printed) =="
python3 -c "import os; v=os.environ.get('OPENAI_API_KEY') or ''; print('OPENAI len:', len(v), '| long enough (>=9):', 1 if len(v) > 8 else 0)"
echo "== 2) openai_adapter_smoke =="
./scripts/openai_adapter_smoke_v1.sh
echo "== 3) GET $U (JSON redacted: sk-*, Bearer …) =="
if ! out="$(curl -sS -S --connect-timeout 5 "$U")"; then
  echo "curl failed (is Pattern Game web up on this host?)." >&2
  exit 1
fi
if [ -z "$out" ]; then
  echo "empty response from $U" >&2
  exit 1
fi
printf '%s\n' "$out" | python3 "$(dirname "$0")/verify_pattern_game_openai_status_redact_v1.py"
