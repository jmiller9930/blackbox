#!/usr/bin/env bash
# Create NDE_ROOT/.venv-train and install FinQuant training deps (torch, etc.).
# LangGraph stays in NDE_ROOT/.venv — orchestration vs training separation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NDE_ROOT="${NDE_ROOT:-/data/NDE}"
REPO_ROOT="${REPO_ROOT:-${HOME}/blackbox}"
VENV="${NDE_ROOT}/.venv-train"
REQ="${REPO_ROOT}/finquant/requirements-finquant-training.txt"

if [[ ! -f "${REQ}" ]]; then
  echo "error: missing ${REQ} (finquant training requirements)" >&2
  exit 1
fi

mkdir -p "${NDE_ROOT}"

# --copies: embed interpreter under NDE_ROOT so bind-mounted .venv-train works when invoked from
# Docker (default venv symlinks python3 -> /usr/bin/python3, which does not exist in slim images).
if [[ ! -x "${VENV}/bin/python" ]]; then
  rm -rf "${VENV}"
  if ! python3 -m venv --copies "${VENV}"; then
    echo "warn: standard venv failed (often missing python3-venv/ensurepip); retrying --without-pip + get-pip" >&2
    rm -rf "${VENV}"
    python3 -m venv --copies --without-pip "${VENV}"
    GET_PIP="$(mktemp /tmp/get-pip-nde-train.XXXXXX.py)"
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "${GET_PIP}"
    "${VENV}/bin/python" "${GET_PIP}"
    rm -f "${GET_PIP}"
  fi
fi

"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install -r "${REQ}"
echo "TRAIN_VENV_READY=${VENV}"
