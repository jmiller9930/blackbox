#!/usr/bin/env bash
# Run ON trx40 after: ssh vanayr@172.20.1.66
# Optional: tmux new -s finquant   then run this script inside tmux.
#
# Container (host launches training/docker/run_smoke.sh): FINQUANT_CONTAINER=1 is set — skips venv,
# git pull, and pip (image already has deps).
#
# Override paths if needed:
#   export BLACKBOX_REPO_ROOT=/home/vanayr/blackbox
#   export FINQUANT_BASE=/data/NDE/finquant/agentic_v05
#   export FINQUANT_VENV=/data/NDE/finquant/.venv-finquant
#   export USE_REPO_CORPUS=1   # if corpus/memory not copied under FINQUANT_BASE yet

set -euo pipefail

BLACKBOX_REPO_ROOT="${BLACKBOX_REPO_ROOT:-${HOME}/blackbox}"
FINQUANT_BASE="${FINQUANT_BASE:-/data/NDE/finquant/agentic_v05}"
FINQUANT_VENV="${FINQUANT_VENV:-/data/NDE/finquant/.venv-finquant}"

CONTAINER_MODE=0
if [[ "${FINQUANT_CONTAINER:-0}" == "1" ]] || [[ -f /.dockerenv ]]; then
  CONTAINER_MODE=1
fi

if [[ "$CONTAINER_MODE" == "1" ]]; then
  cd "${BLACKBOX_REPO_ROOT}"
  echo "[finquant] container mode: using image Python (no venv / no pip install / no git pull)"
else
  mkdir -p "$(dirname "$FINQUANT_VENV")"
  if [[ ! -f "$FINQUANT_VENV/bin/activate" ]]; then
    echo "Creating or repairing venv at $FINQUANT_VENV (missing bin/activate)"
    rm -rf "$FINQUANT_VENV"
    python3 -m venv "$FINQUANT_VENV"
  fi
  # shellcheck source=/dev/null
  source "$FINQUANT_VENV/bin/activate"

  cd "$BLACKBOX_REPO_ROOT"
  if [[ "${FINQUANT_SKIP_GIT_PULL:-0}" != "1" ]]; then
    git pull origin main
  else
    echo "[finquant] FINQUANT_SKIP_GIT_PULL=1 — skipping git pull"
  fi
  pip install -r training/requirements-finquant-training.txt
fi

export BLACKBOX_REPO_ROOT
export FINQUANT_BASE

EXTRA=()
if [[ "${USE_REPO_CORPUS:-0}" == "1" ]]; then
  EXTRA+=(--corpus "$BLACKBOX_REPO_ROOT/training/corpus_v05_agentic_seed.jsonl")
  EXTRA+=(--memory-store "$BLACKBOX_REPO_ROOT/training/finquant_memory/exemplar_store.jsonl")
fi

ADAPTER="${FINQUANT_SMOKE_ADAPTER:-adapters/finquant-1-qwen7b-v0.1-smoke}"

python3 training/test.py \
  --train smoke \
  --adapter "$ADAPTER" \
  --exam-write-report \
  "${EXTRA[@]}"

echo "Done. Expect last line: FINQUANT_RTX40_EVENT_COMPLETE_TRAIN_SMOKE"
