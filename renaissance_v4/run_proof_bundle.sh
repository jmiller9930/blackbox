#!/usr/bin/env bash
# Full baseline proof sequence (architect): ingest + one replay, then two replays for determinism.
# Run from repo root; multi-hour window (Binance ~730d SOLUSDT 5m). Primary host: clawbot.
# Handoff: baseline_v1.md + two matching [VALIDATION_CHECKSUM] lines + sanity answers (see README).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

echo "[PROOF] Repository: $ROOT"
echo "[PROOF] git HEAD: $(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
if [[ "${RENAISSANCE_V4_EXPORT_OUTCOMES:-}" == "1" ]]; then
  echo "[PROOF] RENAISSANCE_V4_EXPORT_OUTCOMES=1 — each replay writes renaissance_v4/reports/outcomes_full.jsonl"
fi

echo "[PROOF] Step 1/2: run_full_validation.sh (init → ingest ~730d SOLUSDT 5m → validate → replay)"
./renaissance_v4/run_full_validation.sh

echo "[PROOF] Step 2/2: run_replay_twice_check.sh — save terminal output; both [VALIDATION_CHECKSUM] lines must match exactly"
./renaissance_v4/run_replay_twice_check.sh

echo "[PROOF] Done."
echo "[PROOF] Artifacts: renaissance_v4/reports/baseline_v1.md (required); outcomes_full.jsonl if export was enabled."
echo "[PROOF] Optional full ledger re-run: RENAISSANCE_V4_EXPORT_OUTCOMES=1 $ROOT/renaissance_v4/run_proof_bundle.sh"
