#!/usr/bin/env bash
# NDE Studio — plain Docker (no docker-compose required).
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
  -v "${NDE_HOST}:/data/NDE"
  -v "${REPO_HOST}:/repo:ro"
)

if [[ "${FOREGROUND}" == true ]]; then
  echo "Running (foreground). Ctrl+C to stop."
  exec docker run --rm -it "${RUN_ARGS[@]}" "${IMAGE}"
fi

docker run -d "${RUN_ARGS[@]}" --restart unless-stopped "${IMAGE}"
echo "Started ${NAME} — http://127.0.0.1:${PORT}"
echo "Logs: docker logs -f ${NAME}"
