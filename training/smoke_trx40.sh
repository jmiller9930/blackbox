#!/usr/bin/env bash
# Run ON trx40 after: ssh vanayr@172.20.1.66
# Optional: tmux new -s finquant   then run this script inside tmux.
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

if [[ ! -d "$FINQUANT_VENV" ]]; then
  echo "Creating venv at $FINQUANT_VENV"
  python3 -m venv "$FINQUANT_VENV"
fi
# shellcheck source=/dev/null
source "$FINQUANT_VENV/bin/activate"

cd "$BLACKBOX_REPO_ROOT"
git pull origin main
pip install -r training/requirements-finquant-training.txt

export BLACKBOX_REPO_ROOT
export FINQUANT_BASE

EXTRA=()
if [[ "${USE_REPO_CORPUS:-0}" == "1" ]]; then
  EXTRA+=(--corpus "$BLACKBOX_REPO_ROOT/training/corpus_v05_agentic_seed.jsonl")
  EXTRA+=(--memory-store "$BLACKBOX_REPO_ROOT/training/finquant_memory/exemplar_store.jsonl")
fi

python3 training/test.py \
  --train smoke \
  --adapter adapters/finquant-agentic-v05-smoke \
  --exam-write-report \
  "${EXTRA[@]}"

echo "Done. Expect last line: FINQUANT_RTX40_EVENT_COMPLETE_TRAIN_SMOKE"
