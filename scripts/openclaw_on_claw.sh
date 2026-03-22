#!/usr/bin/env bash
# OpenClaw CLI is not always on PATH over non-interactive SSH; the checked-out
# repo at ~/openclaw exposes openclaw.mjs. This wrapper forwards all args.
#
# Usage (on clawbot):
#   ~/blackbox/scripts/openclaw_on_claw.sh skills list
#   ~/blackbox/scripts/openclaw_on_claw.sh skills info cody_planner
set -euo pipefail

OPENCLAW_HOME="${OPENCLAW_HOME:-${HOME}/openclaw}"
CLI="${OPENCLAW_HOME}/openclaw.mjs"

if [[ ! -f "${CLI}" ]]; then
  echo "error: missing ${CLI} (set OPENCLAW_HOME or clone openclaw to ~/openclaw)" >&2
  exit 1
fi

exec node "${CLI}" "$@"
