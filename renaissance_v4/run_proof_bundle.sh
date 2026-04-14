#!/usr/bin/env bash
# Full baseline proof sequence (architect): ingest + one replay, then two replays for determinism.
# Run from repo root context; may take hours (Binance backfill). See renaissance_v4/README.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

echo "[PROOF] Step 1/2: run_full_validation.sh (init → ingest ~2y SOLUSDT 5m → validate → replay)"
./renaissance_v4/run_full_validation.sh

echo "[PROOF] Step 2/2: run_replay_twice_check.sh — capture both [VALIDATION_CHECKSUM] lines; they must match"
./renaissance_v4/run_replay_twice_check.sh

echo "[PROOF] Done. Review renaissance_v4/reports/baseline_v1.md; optional full ledger: RENAISSANCE_V4_EXPORT_OUTCOMES=1 replay"
