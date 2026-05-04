#!/usr/bin/env bash
# Unified FinQuant cycle: (optional) export → merge → validate → (optional) QLoRA train.
#
# Design: change **inputs** via env vars; rerun the same commands every campaign.
#
# Prerequisites (trx40):
#   cd "$BLACKBOX_REPO_ROOT"
#   source /data/NDE/finquant/.venv-finquant/bin/activate   # or set VENV_ACTIVATE
#
# Typical — build merged corpus only:
#   export BLACKBOX_REPO_ROOT=/home/vanayr/blackbox
#   export FINQUANT_BASE=/data/NDE/finquant/agentic_v05
#   export MERGED_JSONL="$FINQUANT_BASE/datasets/merged_finquant_v0.2.jsonl"
#   ./training/run_finquant_cycle.sh prepare
#   ./training/run_finquant_cycle.sh validate
#
# Typical — full train + exam (after prepare+validate):
#   export CONFIRM_PRODUCTION_TRAIN=1
#   ./training/run_finquant_cycle.sh train-full
#
# Inputs you swap per campaign:
#   LEDGER_JSON     — optional explicit *_decisions.json; if unset, exporter uses --latest
#   MERGED_JSONL    — output merged JSONL (required for prepare/validate/train-*)
#   INCLUDE_SEED    — if 1, prepend training/corpus_v05_agentic_seed.jsonl (default: 1)
#   EXPORT_GOOD_ONLY — if 1, pass --good-only to exporter (default: 1)
#   EXPORT_MIN_SPREAD — default 0.20
#   TRAIN_LOG       — if set, tee train output to this file
#   RESUME_TRAIN    — if 1, pass --resume-training (continue from latest checkpoint-* under output_dir)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${BLACKBOX_REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
FINQUANT_BASE="${FINQUANT_BASE:-/data/NDE/finquant/agentic_v05}"
EXPORTER="${REPO_ROOT}/prove_learning/finquant/unified/agent_lab/export_to_training_corpus.py"
SEED_JSONL="${REPO_ROOT}/training/corpus_v05_agentic_seed.jsonl"
TMP_EXPORT="${FINQUANT_BASE}/datasets/_tmp_export_$$.jsonl"

INCLUDE_SEED="${INCLUDE_SEED:-1}"
EXPORT_GOOD_ONLY="${EXPORT_GOOD_ONLY:-1}"
EXPORT_MIN_SPREAD="${EXPORT_MIN_SPREAD:-0.20}"

usage() {
  sed -n '2,/^$/p' "$0" | head -35
  echo "Commands: prepare | validate | train-smoke | train-full | help"
}

if [[ "${1:-}" == "help" || "${1:-}" == "-h" || "${1:-}" == "--help" || -z "${1:-}" ]]; then
  usage
  exit 0
fi

cmd="$1"
shift || true

require_merged() {
  if [[ -z "${MERGED_JSONL:-}" ]]; then
    echo "ERROR: set MERGED_JSONL to the merged corpus path (e.g. \$FINQUANT_BASE/datasets/merged_finquant_v0.2.jsonl)" >&2
    exit 2
  fi
}

maybe_venv() {
  if [[ -n "${VENV_ACTIVATE:-}" ]]; then
    # shellcheck source=/dev/null
    source "$VENV_ACTIVATE"
  fi
}

prepare() {
  require_merged
  [[ -f "$EXPORTER" ]] || { echo "ERROR: missing exporter $EXPORTER" >&2; exit 2; }
  mkdir -p "${FINQUANT_BASE}/datasets"

  EXP_ARGS=(--output "$TMP_EXPORT" --min-confidence-spread "$EXPORT_MIN_SPREAD")
  if [[ "${EXPORT_GOOD_ONLY}" == "1" ]]; then
    EXP_ARGS+=(--good-only)
  fi
  if [[ -n "${LEDGER_JSON:-}" ]]; then
    EXP_ARGS+=(--ledger "$LEDGER_JSON")
  else
    EXP_ARGS+=(--latest)
  fi

  echo "=== EXPORT → $TMP_EXPORT"
  (cd "$REPO_ROOT" && python3 "$EXPORTER" "${EXP_ARGS[@]}")

  echo "=== MERGE → $MERGED_JSONL"
  : >"$MERGED_JSONL"
  if [[ "$INCLUDE_SEED" == "1" ]]; then
    [[ -f "$SEED_JSONL" ]] || { echo "ERROR: missing seed $SEED_JSONL" >&2; exit 2; }
    cat "$SEED_JSONL" >>"$MERGED_JSONL"
  fi
  cat "$TMP_EXPORT" >>"$MERGED_JSONL"
  rm -f "$TMP_EXPORT"

  lines=$(wc -l <"$MERGED_JSONL" | tr -d ' ')
  echo "=== MERGED lines: $lines"
}

validate_corpus() {
  require_merged
  [[ -f "$MERGED_JSONL" ]] || { echo "ERROR: missing $MERGED_JSONL — run prepare first" >&2; exit 2; }
  echo "=== VALIDATE $MERGED_JSONL"
  (cd "$REPO_ROOT" && python3 training/validate_agentic_corpus_v1.py "$MERGED_JSONL")
}

train_smoke() {
  require_merged
  maybe_venv
  echo "=== TRAIN smoke + exam"
  if [[ -n "${TRAIN_LOG:-}" ]]; then
    mkdir -p "$(dirname "$TRAIN_LOG")"
    (cd "$REPO_ROOT" && \
      export BLACKBOX_REPO_ROOT="$REPO_ROOT" FINQUANT_BASE="$FINQUANT_BASE" && \
      python3 training/test.py --train smoke \
        --adapter adapters/finquant-1-qwen7b-v0.1-smoke \
        --exam-write-report \
        --dataset "$MERGED_JSONL" 2>&1 | tee -a "$TRAIN_LOG")
  else
    (cd "$REPO_ROOT" && \
      export BLACKBOX_REPO_ROOT="$REPO_ROOT" FINQUANT_BASE="$FINQUANT_BASE" && \
      python3 training/test.py --train smoke \
        --adapter adapters/finquant-1-qwen7b-v0.1-smoke \
        --exam-write-report \
        --dataset "$MERGED_JSONL")
  fi
}

train_full() {
  require_merged
  if [[ "${CONFIRM_PRODUCTION_TRAIN:-}" != "1" ]]; then
    echo "ERROR: set CONFIRM_PRODUCTION_TRAIN=1 for train-full" >&2
    exit 2
  fi
  maybe_venv
  RESUME_ARGS=()
  if [[ "${RESUME_TRAIN:-}" == "1" ]]; then
    RESUME_ARGS+=(--resume-training)
    echo "=== RESUME_TRAIN=1 — continuing from latest checkpoint under adapters/finquant-1-qwen7b-v0.1"
  fi
  echo "=== TRAIN full + exam (production)"
  if [[ -n "${TRAIN_LOG:-}" ]]; then
    mkdir -p "$(dirname "$TRAIN_LOG")"
    (cd "$REPO_ROOT" && \
      export BLACKBOX_REPO_ROOT="$REPO_ROOT" FINQUANT_BASE="$FINQUANT_BASE" && \
      python3 training/test.py --train full --confirm-production-train \
        --adapter adapters/finquant-1-qwen7b-v0.1 \
        --exam-write-report \
        --dataset "$MERGED_JSONL" "${RESUME_ARGS[@]}" 2>&1 | tee -a "$TRAIN_LOG")
  else
    (cd "$REPO_ROOT" && \
      export BLACKBOX_REPO_ROOT="$REPO_ROOT" FINQUANT_BASE="$FINQUANT_BASE" && \
      python3 training/test.py --train full --confirm-production-train \
        --adapter adapters/finquant-1-qwen7b-v0.1 \
        --exam-write-report \
        --dataset "$MERGED_JSONL" "${RESUME_ARGS[@]}")
  fi
}

case "$cmd" in
  prepare) prepare ;;
  validate) validate_corpus ;;
  train-smoke) train_smoke ;;
  train-full) train_full ;;
  help|-h|--help) usage ;;
  *) echo "Unknown command: $cmd" >&2; usage; exit 2 ;;
esac
