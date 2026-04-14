#!/usr/bin/env bash
# Full pipeline: init DB, ingest (long), validate, replay. Run from anywhere; resolves repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

echo "[VALIDATION] Starting"

python3 renaissance_v4/data/init_db.py
python3 renaissance_v4/data/binance_ingest.py
python3 renaissance_v4/data/bar_validator.py
python3 renaissance_v4/research/replay_runner.py

echo "[VALIDATION] Completed"
