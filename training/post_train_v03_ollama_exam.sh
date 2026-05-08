#!/usr/bin/env bash
# trx40: post v0.3 full train — digest, merge adapter into Ollama, adversarial exam.
# Run in tmux: tmux new -s fq_v03_merge_exam bash ~/blackbox/training/post_train_v03_ollama_exam.sh

set -euo pipefail
export FINQUANT_BASE="${FINQUANT_BASE:-/data/NDE/finquant/agentic_v05}"
source /data/NDE/finquant/.venv-finquant/bin/activate
cd "${HOME}/blackbox"
mkdir -p "${FINQUANT_BASE}/reports/exam_results"

echo "[v03] Post-run digest…"
python3 "${HOME}/blackbox/training/finquant_post_run_digest.py" \
  --base "${FINQUANT_BASE}" \
  --adapter adapters/finquant-1-qwen7b-v0.3 \
  2>&1 | tee "${FINQUANT_BASE}/reports/digest_v03.log"

echo "[v03] Merge adapter → Ollama…"
python3 "${HOME}/blackbox/training/merge_adapter_to_ollama.py" \
  --adapter "${FINQUANT_BASE}/adapters/finquant-1-qwen7b-v0.3" \
  --merged-out "${FINQUANT_BASE}/models/finquant-1-qwen7b-v0.3-merged" \
  --model-tag finquant-1-qwen7b-v0.3 \
  --ollama-url http://localhost:11434 \
  2>&1 | tee "${FINQUANT_BASE}/reports/merge_v03.log"

echo "[v03] Adversarial exam (frozen v3 pack)…"
python3 "${HOME}/blackbox/training/exams/finquant_exam_proctor.py" \
  --cases "${HOME}/blackbox/training/exams/finquant_adversarial_exam_v1_cases.jsonl" \
  --model finquant-1-qwen7b-v0.3 \
  --ollama-url http://localhost:11434 \
  --out "${FINQUANT_BASE}/reports/exam_results/" \
  --run-label finquant_v0.3_certification \
  --timeout 180 \
  2>&1 | tee "${FINQUANT_BASE}/reports/exam_results/exam_v03.log"

proc_exit=${PIPESTATUS[0]:-1}
echo "JOB_ALL_DONE (proctor_exit=${proc_exit})" | tee -a "${FINQUANT_BASE}/reports/exam_results/exam_v03.log"
exit "${proc_exit}"
