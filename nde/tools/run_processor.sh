#!/usr/bin/env bash
# Run nde_source_processor.py with the canonical /data/NDE/.venv Python.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="/data/NDE/.venv"

if [[ ! -d "${VENV}" ]]; then
  bash "${SCRIPT_DIR}/setup_env.sh"
fi

exec "${VENV}/bin/python" /data/NDE/tools/nde_source_processor.py "$@"
