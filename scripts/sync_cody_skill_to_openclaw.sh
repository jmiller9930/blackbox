#!/usr/bin/env bash
# Sync the in-repo Cody skill into OpenClaw's workspace skills directory.
# Run on the Claw host after `git pull` (OpenClaw rejects symlinks that escape the workspace root).
#
# Usage:
#   ./scripts/sync_cody_skill_to_openclaw.sh
#   OPENCLAW_WORKSPACE=/path/to/workspace ./scripts/sync_cody_skill_to_openclaw.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/agents/cody/skills/cody-planner"
DST_ROOT="${OPENCLAW_WORKSPACE:-${HOME}/.openclaw/workspace}/skills/cody-planner"

if [[ ! -f "${SRC}/SKILL.md" ]]; then
  echo "error: missing ${SRC}/SKILL.md (run from repo root?)" >&2
  exit 1
fi

mkdir -p "$(dirname "${DST_ROOT}")"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "${SRC}/" "${DST_ROOT}/"
else
  rm -rf "${DST_ROOT}"
  mkdir -p "${DST_ROOT}"
  cp -a "${SRC}/." "${DST_ROOT}/"
fi

echo "Synced Cody skill:"
echo "  ${SRC}/"
echo "  -> ${DST_ROOT}/"
echo "Verify: cd \"\${HOME}/openclaw\" && node openclaw.mjs skills info cody_planner"
