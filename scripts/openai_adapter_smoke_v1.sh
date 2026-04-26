#!/usr/bin/env sh
# OpenAI Responses adapter smoke (GT_DIRECTIVE_026AI). Avoids ``python -m`` runpy warning.
# Requires OPENAI_API_KEY (or host ``~/.blackbox_secrets/openai.env`` per adapter). From repo root:
#   ./scripts/openai_adapter_smoke_v1.sh
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=.
exec python3 -c "import json; from renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 import run_smoke_test_strict_json_v1 as s; r=s(); print(json.dumps({k:v for k,v in r.items() if k!='key'}, indent=2))"
