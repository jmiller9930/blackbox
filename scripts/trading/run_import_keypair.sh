#!/usr/bin/env bash
# Run import_solana_keypair.py from repo root (works even if you invoke from trading_core).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"
exec python3 "$REPO_ROOT/scripts/trading/import_solana_keypair.py" "$@"
