#!/usr/bin/env bash
# Proof gate — local DeepSeek R1 reviewer model must appear in Ollama tags and /api/generate must succeed.
# Usage (from any machine that can reach the reviewer host):
#   ./scripts/verify_deepseek_escalation_ollama_v1.sh
# Optional:
#   DEEPSEEK_ESCALATION_OLLAMA_BASE_URL=http://172.20.2.230:11434 DEEPSEEK_ESCALATION_OLLAMA_MODEL=deepseek-r1:14b ./scripts/verify_deepseek_escalation_ollama_v1.sh
#
# Exit 0 only if both checks pass. Operator: install on host first — typically:
#   ollama pull deepseek-r1:14b

set -euo pipefail
BASE="${DEEPSEEK_ESCALATION_OLLAMA_BASE_URL:-http://172.20.2.230:11434}"
BASE="${BASE%/}"
MODEL="${DEEPSEEK_ESCALATION_OLLAMA_MODEL:-deepseek-r1:14b}"

echo "verify_deepseek_escalation_ollama_v1: BASE=$BASE MODEL=$MODEL"

echo "--- GET /api/tags (grep model name) ---"
TAGS=$(curl -sS --connect-timeout 15 --max-time 60 "${BASE}/api/tags") || {
  echo "FAIL: could not fetch /api/tags"
  exit 1
}
if ! echo "$TAGS" | python3 -c "import json,sys; d=json.load(sys.stdin); names=[m.get('name','') for m in d.get('models',[])]; sys.exit(0 if '${MODEL}' in names else 1)"; then
  echo "FAIL: model '${MODEL}' not listed in /api/tags"
  echo "$TAGS" | python3 -c "import json,sys; d=json.load(sys.stdin); print([m['name'] for m in d.get('models',[])])" 2>/dev/null || echo "$TAGS" | head -c 500
  exit 1
fi
echo "OK: '${MODEL}' appears in /api/tags"

echo "--- POST /api/generate (non-streaming smoke) ---"
GEN_PAYLOAD=$(MODEL="$MODEL" python3 <<'PY'
import json, os
print(
    json.dumps(
        {
            "model": os.environ["MODEL"],
            "prompt": "Reply with exactly: OK",
            "stream": False,
        },
        ensure_ascii=False,
    )
)
PY
)
GEN=$(curl -sS --connect-timeout 15 --max-time 180 -X POST "${BASE}/api/generate" \
  -H 'Content-Type: application/json' \
  -d "$GEN_PAYLOAD") || {
  echo "FAIL: generate request failed"
  exit 1
}
if echo "$GEN" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('done') is True and not d.get('error') else 1)" 2>/dev/null; then
  echo "OK: /api/generate succeeded"
  echo "$GEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print('  model field:', d.get('model')); print('  response preview:', repr((d.get('response') or '')[:120]))"
  exit 0
fi
echo "FAIL: /api/generate did not return done=true or returned error"
echo "$GEN" | head -c 1200
exit 1
