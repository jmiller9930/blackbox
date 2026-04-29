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

rm -rf "${VENV}"
if ! python3 -m venv "${VENV}"; then
  echo "warn: standard venv failed (often missing python3-venv/ensurepip); retrying --without-pip + get-pip" >&2
  rm -rf "${VENV}"
  python3 -m venv --without-pip "${VENV}"
  GET_PIP="$(mktemp /tmp/get-pip-nde.XXXXXX.py)"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "${GET_PIP}"
  "${VENV}/bin/python" "${GET_PIP}"
  rm -f "${GET_PIP}"
fi

"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install -r "${REQ}"
echo "VENV_READY=${VENV}"
