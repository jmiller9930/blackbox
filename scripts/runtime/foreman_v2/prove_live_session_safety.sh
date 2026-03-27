#!/usr/bin/env bash
set -euo pipefail

# Live proof harness for architect validation.
# Requires sourced .env.foreman_v2 with live session values.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${RUNTIME_DIR}/../.." && pwd)"
DOCS_DIR="${REPO_ROOT}/docs/working"

cd "${RUNTIME_DIR}"

if [ -f "${REPO_ROOT}/.env.foreman_v2" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env.foreman_v2"
fi

required=(MISSION_CONTROL_URL FOREMAN_V2_DEVELOPER_SESSION FOREMAN_V2_ARCHITECT_SESSION)
for key in "${required[@]}"; do
  if [ -z "${!key:-}" ]; then
    echo "missing required env: ${key}"
    exit 2
  fi
done

unset FOREMAN_V2_DRY_RUN
export FOREMAN_V2_STRICT_SESSION_GUARD="${FOREMAN_V2_STRICT_SESSION_GUARD:-1}"

echo "proof: host=$(hostname)"
echo "proof: repo=$(cd "${REPO_ROOT}" && pwd)"
echo "proof: sha=$(cd "${REPO_ROOT}" && git rev-parse HEAD)"

python3 -m foreman_v2 status || true

python3 -m foreman_v2 route --actor developer --message "proof:developer:1"
python3 -m foreman_v2 route --actor developer --message "proof:developer:2"
python3 -m foreman_v2 route --actor architect --message "proof:architect:1"
python3 -m foreman_v2 broadcast --message "proof:broadcast:1"

if [ -f "${DOCS_DIR}/foreman_v2_session_lock.json" ]; then
  echo "proof: session lock file present"
  python3 -m json.tool "${DOCS_DIR}/foreman_v2_session_lock.json"
else
  echo "proof: session lock file missing"
fi

echo "proof: audit tail"
python3 - "$DOCS_DIR/foreman_v2_audit.jsonl" <<'PY'
import pathlib
import sys

p = pathlib.Path(sys.argv[1])
if not p.exists():
    print("audit missing")
    raise SystemExit(0)
lines = p.read_text(encoding="utf-8").splitlines()
for line in lines[-40:]:
    print(line)
PY

python3 -m foreman_v2 terminate || true
python3 -m foreman_v2 status || true

echo "proof: complete"

