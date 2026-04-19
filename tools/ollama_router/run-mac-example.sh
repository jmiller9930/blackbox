#!/usr/bin/env bash
# Example: router + repo context on Mac Docker. Adjust BLACKBOX path if needed.
set -euo pipefail
BLACKBOX="${BLACKBOX:-$HOME/Documents/code_projects/blackbox}"
docker rm -f ollama-router 2>/dev/null || true
docker build -t ollama-router:local "$(dirname "$0")"
docker run -d --name ollama-router -p 11437:8080 \
  -e OLLAMA_UPSTREAM=http://host.docker.internal:11435 \
  -e ROUTER_MODEL_CODE=qwen3-coder:30b \
  -e ROUTER_MODEL_THEORY=qwen3-coder-next:latest \
  -e ROUTER_CONTEXT_ROOT=/project \
  -e ROUTER_CONTEXT_FILES="${ROUTER_CONTEXT_FILES:-README.md,AGENTS.md}" \
  -v "${BLACKBOX}:/project:ro" \
  ollama-router:local
echo "Router on :11437 — set Open WebUI Ollama URL to http://host.docker.internal:11437"
echo "Repo mounted read-only at /project — edit ROUTER_CONTEXT_FILES to add paths."
