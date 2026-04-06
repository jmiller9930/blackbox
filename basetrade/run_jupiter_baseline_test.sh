#!/usr/bin/env bash
# Jupiter policy baseline parity test — run from anywhere; uses repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/scripts/runtime:${ROOT}"
cd "$ROOT"
exec python3 basetrade/jupiter_baseline_signal_test.py "$@"
