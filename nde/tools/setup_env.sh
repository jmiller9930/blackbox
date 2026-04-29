#!/usr/bin/env bash
# Create /data/NDE/.venv and install processor deps from requirements next to this script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="/data/NDE/.venv"
REQ="${SCRIPT_DIR}/requirements.txt"

if [[ ! -f "${REQ}" ]]; then
  echo "error: missing ${REQ} (run scripts/install_nde_data_layout.sh /data/NDE)" >&2
  exit 1
fi

python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install -r "${REQ}"
echo "VENV_READY=${VENV}"
