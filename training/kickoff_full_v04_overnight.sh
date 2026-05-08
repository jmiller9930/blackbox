#!/usr/bin/env bash
# trx40: full QLoRA (3000 steps) for finquant-1-qwen7b-v0.4 on merged_finquant_v0.5.jsonl.
# Run after smoke passes. Prefer tmux.
#
#   tmux new -s fq_v04_full 'bash ~/blackbox/training/kickoff_full_v04_overnight.sh'

set -euo pipefail
export FINQUANT_BASE="${FINQUANT_BASE:-/data/NDE/finquant/agentic_v05}"
source /data/NDE/finquant/.venv-finquant/bin/activate
cd "${HOME}/blackbox"
git pull origin main

REPO="${HOME}/blackbox"
MERGED="${FINQUANT_BASE}/datasets/merged_finquant_v0.5.jsonl"

echo "[v04 full] Refresh merge → ${MERGED}"
cat "${FINQUANT_BASE}/datasets/train_agentic_v1.jsonl" \
  "${REPO}/training/remediation_corpus_v0.4.jsonl" \
  "${REPO}/training/remediation_json_surface_v05.jsonl" \
  > "${MERGED}"
wc -l "${MERGED}"

python3 "${REPO}/training/validate_agentic_corpus_v1.py" "${MERGED}" \
  --store "${REPO}/training/finquant_memory/exemplar_store.jsonl"

echo "[v04 full] train_qlora full (3000 steps) → finquant-1-qwen7b-v0.4"
python3 "${REPO}/training/train_qlora.py" full \
  --config "${REPO}/training/config_v0.4.yaml" \
  --dataset "${MERGED}" \
  --base "${FINQUANT_BASE}" \
  2>&1 | tee "${FINQUANT_BASE}/reports/train_v04.log"

echo "TRAIN_V04_ALL_DONE" | tee -a "${FINQUANT_BASE}/reports/train_v04.log"
