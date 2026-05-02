#!/usr/bin/env bash
# Host-side: run FinQuant smoke inside the GPU container.
#
# Prerequisites on trx40: NVIDIA driver + nvidia-container-toolkit; Docker able to use --gpus all.
#
# Usage (repo root or any cwd — script resolves paths):
#   ./training/docker/run_smoke.sh
#
# Env:
#   FINQUANT_TRAIN_IMAGE   image tag (default blackbox-finquant-train:rtx40)
#   FINQUANT_BASE_HOST     host path for adapter/datasets (default /data/NDE/finquant/agentic_v05)
#   BLACKBOX_REPO_HOST     host path to blackbox clone (default ~/blackbox resolved)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${FINQUANT_TRAIN_IMAGE:-blackbox-finquant-train:rtx40}"
FINQUANT_BASE_HOST="${FINQUANT_BASE_HOST:-/data/NDE/finquant/agentic_v05}"
BLACKBOX_REPO_HOST="${BLACKBOX_REPO_HOST:-$HOME/blackbox}"

if [[ ! -d "$BLACKBOX_REPO_HOST" ]]; then
  echo "ERROR: BLACKBOX_REPO_HOST not found: $BLACKBOX_REPO_HOST" >&2
  exit 2
fi
mkdir -p "$FINQUANT_BASE_HOST"

docker run --rm -it \
  --gpus all \
  --shm-size=8g \
  -v "$BLACKBOX_REPO_HOST:/workspace/blackbox:rw" \
  -v "$FINQUANT_BASE_HOST:/data/NDE/finquant/agentic_v05:rw" \
  -e BLACKBOX_REPO_ROOT=/workspace/blackbox \
  -e FINQUANT_BASE=/data/NDE/finquant/agentic_v05 \
  -e FINQUANT_CONTAINER=1 \
  -e USE_REPO_CORPUS="${USE_REPO_CORPUS:-1}" \
  -w /workspace/blackbox \
  "$IMAGE" \
  bash training/smoke_trx40.sh
