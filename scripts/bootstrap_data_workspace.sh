#!/usr/bin/env bash
# Copy DATA agent markdown + data-guardian skill into a dedicated OpenClaw workspace.
# Usage: ./scripts/bootstrap_data_workspace.sh
#   OPENCLAW_WORKSPACE_DATA=~/.openclaw/workspace-data ./scripts/bootstrap_data_workspace.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="${OPENCLAW_WORKSPACE_DATA:-${HOME}/.openclaw/workspace-data}"
SRC="${ROOT}/agents/data"
SKILL_SRC="${SRC}/skills/data-guardian"
SKILL_DST="${DST}/skills/data-guardian"

for f in IDENTITY.md SOUL.md TOOLS.md AGENTS.md USER.md; do
  if [[ ! -f "${SRC}/${f}" ]]; then
    echo "error: missing ${SRC}/${f}" >&2
    exit 1
  fi
done
mkdir -p "${DST}" "${SKILL_DST}"
cp -a "${SRC}/IDENTITY.md" "${SRC}/SOUL.md" "${SRC}/TOOLS.md" "${SRC}/AGENTS.md" "${SRC}/USER.md" "${DST}/"
if [[ -f "${SKILL_SRC}/SKILL.md" ]]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "${SKILL_SRC}/" "${SKILL_DST}/"
  else
    rm -rf "${SKILL_DST}"
    mkdir -p "${SKILL_DST}"
    cp -a "${SKILL_SRC}/." "${SKILL_DST}/"
  fi
fi
echo "DATA workspace ready:"
echo "  ${DST}/"
echo "  skill -> ${SKILL_DST}/"
echo "Next: add agents.list entry for id=data (see docs/architect/DATA_ONLINE_SETUP.md)"
