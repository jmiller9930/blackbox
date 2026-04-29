#!/usr/bin/env bash
# Install canonical NDE host layout from the repo to /data/NDE (or DEST).
# Safe: copies static tree only; does not touch /data/finquant-1 or running jobs.
set -euo pipefail

DEST="${1:-/data/NDE}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAYOUT="${REPO_ROOT}/nde_factory/layout"

if [[ ! -d "${LAYOUT}" ]]; then
  echo "error: missing layout at ${LAYOUT}" >&2
  exit 1
fi

echo "Installing NDE layout from ${LAYOUT} -> ${DEST}"
mkdir -p "${DEST}"
rsync -a "${LAYOUT}/" "${DEST}/"
echo "Done. Top-level README: ${DEST}/README.md"
