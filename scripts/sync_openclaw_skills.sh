#!/usr/bin/env bash
# Sync in-repo skills into OpenClaw workspace (no symlinks outside workspace).
# Usage: ./scripts/sync_openclaw_skills.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${OPENCLAW_WORKSPACE:-${HOME}/.openclaw/workspace}/skills"

sync_one() {
  local name="$1"
  local src="${ROOT}/agents/${2}/skills/${3}"
  local dst="${WS}/${4}"
  if [[ ! -f "${src}/SKILL.md" ]]; then
    echo "error: missing ${src}/SKILL.md" >&2
    return 1
  fi
  mkdir -p "$(dirname "${dst}")"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "${src}/" "${dst}/"
  else
    rm -rf "${dst}"
    mkdir -p "${dst}"
    cp -a "${src}/." "${dst}/"
  fi
  echo "Synced ${src}/ -> ${dst}/"
}

sync_one "cody" "cody" "cody-planner" "cody-planner"
sync_one "data" "data" "data-guardian" "data-guardian"
echo "Verify: node \"\${HOME}/openclaw/openclaw.mjs\" skills list"
