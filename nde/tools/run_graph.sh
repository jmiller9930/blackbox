#!/usr/bin/env bash
# LangGraph NDE Factory runner (nde_graph_runner.py).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="/data/NDE/.venv"

if [[ ! -d "$VENV" ]]; then
  bash "${SCRIPT_DIR}/setup_env.sh"
fi

exec "${VENV}/bin/python" "${SCRIPT_DIR}/nde_graph_runner.py" "$@"
