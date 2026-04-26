#!/usr/bin/env sh
# Proves: smoke OK, key present in *this* process without echoing the value, and
# GET /api/reasoning-model/status reports openai key diagnostics. Run on the same host/user as
# Pattern Machine Flask, from repo root:
#   ./scripts/verify_pattern_game_openai_v1.sh
# Optional: PATTERN_GAME_STATUS_URL (default http://127.0.0.1:8765/api/reasoning-model/status)
set -e
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=.
U="${PATTERN_GAME_STATUS_URL:-http://127.0.0.1:8765/api/reasoning-model/status}"
echo "== 1) OPENAI_API_KEY length in this process (not printed) =="
python3 -c "import os; v=os.environ.get('OPENAI_API_KEY') or ''; print('OPENAI len:', len(v), '| non-empty:', 1 if len(v) > 8 else 0)"
echo "== 2) openai_adapter_smoke =="
./scripts/openai_adapter_smoke_v1.sh
echo "== 3) reasoning-model status =="
curl -sS -S "$U" | python3 -c "import json, sys; o=json.load(sys.stdin); s=o.get('runtime_signals_v1') or {}; d=s.get('openai_key_diagnostics_v1') or {}; print('ok:', o.get('ok'), 'key_resolved:', d.get('key_resolved'), 'situation:', d.get('situation'), 'primary_code:', o.get('primary_escalation_code_v1'), 'proof:', (o.get('fields_v1') or {}).get('external_api_proof_line_v1'))"
