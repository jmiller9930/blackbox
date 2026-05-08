#!/usr/bin/env bash
# trx40: build merged_finquant_v0.5.jsonl, validate, QLoRA smoke (200 steps) for v0.4 adapter test.
# Does NOT run full train.
#
#   tmux new -s fq_v04_smoke 'bash ~/blackbox/training/kickoff_smoke_v04.sh'

set -euo pipefail
export FINQUANT_BASE="${FINQUANT_BASE:-/data/NDE/finquant/agentic_v05}"
source /data/NDE/finquant/.venv-finquant/bin/activate
cd "${HOME}/blackbox"
git pull origin main

REPO="${HOME}/blackbox"
MERGED="${FINQUANT_BASE}/datasets/merged_finquant_v0.5.jsonl"

echo "[v04 smoke] Merging train + remediation v0.4 + json_surface v05 → ${MERGED}"
cat "${FINQUANT_BASE}/datasets/train_agentic_v1.jsonl" \
  "${REPO}/training/remediation_corpus_v0.4.jsonl" \
  "${REPO}/training/remediation_json_surface_v05.jsonl" \
  > "${MERGED}"
wc -l "${MERGED}"

echo "[v04 smoke] Validate merged…"
python3 "${REPO}/training/validate_agentic_corpus_v1.py" "${MERGED}" \
  --store "${REPO}/training/finquant_memory/exemplar_store.jsonl"

echo "[v04 smoke] train_qlora smoke (200 steps, adapter finquant-1-qwen7b-v0.4-smoke)…"
python3 "${REPO}/training/train_qlora.py" smoke \
  --config "${REPO}/training/config_v0.4.yaml" \
  --dataset "${MERGED}" \
  --base "${FINQUANT_BASE}" \
  2>&1 | tee "${FINQUANT_BASE}/reports/smoke_v04.log"

echo "SMOKE_V04_DONE" | tee -a "${FINQUANT_BASE}/reports/smoke_v04.log"
