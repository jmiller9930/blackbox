#!/usr/bin/env bash
# NDE Studio — plain Docker (no docker-compose required).
# Host policy: canonical UI/container test on lab host 172.20.1.66 (trx40) — not Mac Docker for acceptance (see README.md).
# Usage:
#   ./run-docker.sh              # build + run detached
#   ./run-docker.sh --foreground
#   REPO_HOST=/path/to/blackbox ./run-docker.sh
#
# URL: http://127.0.0.1:3999
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

IMAGE="${NDE_STUDIO_IMAGE:-nde-studio:local}"
NAME="${NDE_STUDIO_CONTAINER:-nde-studio}"
PORT="${NDE_STUDIO_PORT:-3999}"
REPO_HOST="${REPO_HOST:-${HOME}/blackbox}"
NDE_HOST="${NDE_HOST:-/data/NDE}"
FINQUANT_LEGACY_HOST="${FINQUANT_LEGACY_HOST:-/data/finquant-1}"

FOREGROUND=false
for a in "$@"; do
  [[ "$a" == "--foreground" || "$a" == "-f" ]] && FOREGROUND=true
done

echo "Building ${IMAGE} ..."
docker build -t "${IMAGE}" .

docker rm -f "${NAME}" 2>/dev/null || true

RUN_ARGS=(
  --name "${NAME}"
  -p "${PORT}:3999"
  -e PORT=3999
  -e NDE_DATA_ROOT=/data/NDE
  -e REPO_MOUNT=/repo
  -e FINQUANT_LEGACY_ROOT=/data/finquant-1
  -v "${NDE_HOST}:/data/NDE"
  -v "${FINQUANT_LEGACY_HOST}:/data/finquant-1"
  -v "${REPO_HOST}:/repo:ro"
)

# FinQuant eval script uses TRAIN_PYTHON (see /data/NDE/tools/run_finquant_v02_eval.sh).
# Point at a full interpreter on a shared volume (e.g. conda/venv on the host under
# /data/finquant-1 or /data/NDE). Example:
#   TRAIN_PYTHON=/data/finquant-1/.venv/bin/python ./run-docker.sh
[[ -n "${TRAIN_PYTHON:-}" ]] && RUN_ARGS+=( -e "TRAIN_PYTHON=${TRAIN_PYTHON}" )

if [[ "${FOREGROUND}" == true ]]; then
  echo "Running (foreground). Ctrl+C to stop."
  exec docker run --rm -it "${RUN_ARGS[@]}" "${IMAGE}"
fi

docker run -d "${RUN_ARGS[@]}" --restart unless-stopped "${IMAGE}"
echo "Started ${NAME} — http://127.0.0.1:${PORT}"
echo "Logs: docker logs -f ${NAME}"
