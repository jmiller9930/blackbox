#!/usr/bin/env bash
# Determinism: same DB + same code -> identical [VALIDATION_CHECKSUM] (no ingest).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

run_checksum() {
  python3 renaissance_v4/research/replay_runner.py 2>&1 | grep '\[VALIDATION_CHECKSUM\]' | tail -1
}

echo "[DETERMINISM] Run 1"
C1="$(run_checksum)"
echo "$C1"

echo "[DETERMINISM] Run 2"
C2="$(run_checksum)"
echo "$C2"

if [[ "$C1" != "$C2" ]]; then
  echo "[DETERMINISM] FAIL: checksums differ" >&2
  exit 1
fi
echo "[DETERMINISM] OK: checksums match"
