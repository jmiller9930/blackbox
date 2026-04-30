#!/usr/bin/env bash
# FinQuant v0.2 — run eval on the host Python/GPU stack (invoked from NDE Studio via spawn).
# Expects REPO_ROOT (repo checkout), FINQUANT_BASE (legacy finquant tree), TRAIN_PYTHON.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-${HOME}/blackbox}"
FINQUANT_BASE="${FINQUANT_BASE:-/data/finquant-1}"
# Default: training venv on NDE host layout (override with TRAIN_PYTHON).
PY="${TRAIN_PYTHON:-/data/NDE/.venv-train/bin/python}"

cd "${REPO_ROOT}"

echo "Using Python: ${PY}" >&2
"${PY}" --version >&2

exec "${PY}" finquant/evals/eval_finquant.py \
  --adapter "${FINQUANT_BASE}/adapters/finquant-1-qwen7b-v0.2" \
  --write-report \
  --report-path "${FINQUANT_BASE}/reports/v0.2_eval_report.md"
