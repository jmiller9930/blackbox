#!/usr/bin/env bash
set -euo pipefail

# Creates/updates a Foreman v2 env file and optionally runs
# a quick sanity check for required live-dispatch variables.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${RUNTIME_DIR}/../.." && pwd)"

ENV_PATH="${1:-${REPO_ROOT}/.env.foreman_v2}"

touch "${ENV_PATH}"

upsert() {
  local key="$1"
  local value="$2"
  if rg -n "^${key}=" "${ENV_PATH}" >/dev/null 2>&1; then
    python3 - "$ENV_PATH" "$key" "$value" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={value}")
    else:
        out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  else
    printf "%s=%s\n" "$key" "$value" >> "${ENV_PATH}"
  fi
}

# Prefer currently exported env values, fallback to defaults/placeholders.
upsert "MISSION_CONTROL_URL" "${MISSION_CONTROL_URL:-http://localhost:4000}"
upsert "MC_API_TOKEN" "${MC_API_TOKEN:-}"
upsert "FOREMAN_V2_DEVELOPER_SESSION" "${FOREMAN_V2_DEVELOPER_SESSION:-}"
upsert "FOREMAN_V2_ARCHITECT_SESSION" "${FOREMAN_V2_ARCHITECT_SESSION:-}"
upsert "FOREMAN_V2_POLL_SECONDS" "${FOREMAN_V2_POLL_SECONDS:-3}"
upsert "FOREMAN_V2_STRICT_SESSION_GUARD" "${FOREMAN_V2_STRICT_SESSION_GUARD:-1}"
upsert "FOREMAN_V2_DRY_RUN" "${FOREMAN_V2_DRY_RUN:-0}"

echo "Wrote ${ENV_PATH}"
echo "Load it with: source \"${ENV_PATH}\""

required_ok=1
for k in MISSION_CONTROL_URL FOREMAN_V2_DEVELOPER_SESSION FOREMAN_V2_ARCHITECT_SESSION; do
  v="$(python3 - "$ENV_PATH" "$k" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
key = sys.argv[2]
value = ""
for line in path.read_text(encoding="utf-8").splitlines():
    if line.startswith(f"{key}="):
        value = line.split("=", 1)[1].strip()
print(value)
PY
)"
  if [ -z "${v}" ]; then
    echo "MISSING: ${k}"
    required_ok=0
  fi
done

if [ "${required_ok}" -eq 1 ]; then
  echo "Live-dispatch env check: PASS"
else
  echo "Live-dispatch env check: FAIL (fill missing values above)"
fi

