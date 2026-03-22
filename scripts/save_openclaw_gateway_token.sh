#!/usr/bin/env bash
# Prompt once, save OPENCLAW_GATEWAY_TOKEN to ~/.env.local (gitignored).
# Usage: run from repo root: ./scripts/save_openclaw_gateway_token.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env.local"

echo "Paste OpenClaw gateway token, then press Enter:"
read -r TOKEN

if [[ -z "${TOKEN// }" ]]; then
  echo "Empty token, aborting." >&2
  exit 1
fi

umask 077
printf 'OPENCLAW_GATEWAY_TOKEN=%s\n' "$TOKEN" >"$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "Wrote: $ENV_FILE (chmod 600). Do not commit."
