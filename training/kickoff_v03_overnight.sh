#!/usr/bin/env bash
# trx40: merge v0.4 dataset, validate, smoke, then full QLoRA (v0.3 adapter).
# Run inside tmux, e.g.:
#   tmux new -s fq_v03_overnight 'export FINQUANT_BASE=/data/NDE/finquant/agentic_v05 && bash ~/blackbox/training/kickoff_v03_overnight.sh 2>&1 | tee -a $FINQUANT_BASE/reports/tmux_fq_v03.log'

set -euo pipefail
set -o pipefail

export FINQUANT_BASE="${FINQUANT_BASE:-/data/NDE/finquant/agentic_v05}"
source /data/NDE/finquant/.venv-finquant/bin/activate
cd "${HOME}/blackbox"
git pull origin main

REPO="${HOME}/blackbox"
MERGED="${FINQUANT_BASE}/datasets/merged_finquant_v0.4.jsonl"

echo "[v03] Merging train + remediation_corpus_v0.4.jsonl → ${MERGED}"
cat "${FINQUANT_BASE}/datasets/train_agentic_v1.jsonl" \
  "${REPO}/training/remediation_corpus_v0.4.jsonl" > "${MERGED}"
wc -l "${MERGED}"

echo "[v03] Validating merged corpus…"
python3 "${REPO}/training/validate_agentic_corpus_v1.py" "${MERGED}" \
  --store "${REPO}/training/finquant_memory/exemplar_store.jsonl"

echo "[v03] Smoke (200 steps)…"
python3 "${REPO}/training/train_qlora.py" smoke \
  --config "${REPO}/training/config_v0.3.yaml" \
  --dataset "${MERGED}" \
  --base "${FINQUANT_BASE}" \
  2>&1 | tee "${FINQUANT_BASE}/reports/smoke_v03.log"
echo "SMOKE_DONE" | tee -a "${FINQUANT_BASE}/reports/smoke_v03.log"

echo "[v03] Full train (3000 steps)…"
python3 "${REPO}/training/train_qlora.py" full \
  --config "${REPO}/training/config_v0.3.yaml" \
  --dataset "${MERGED}" \
  --base "${FINQUANT_BASE}" \
  2>&1 | tee "${FINQUANT_BASE}/reports/train_v03.log"
echo "TRAIN_ALL_DONE" | tee -a "${FINQUANT_BASE}/reports/train_v03.log"
