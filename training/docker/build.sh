#!/usr/bin/env bash
# Build GPU training image. Run from repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
TAG="${FINQUANT_TRAIN_IMAGE:-blackbox-finquant-train:rtx40}"
docker build -f training/docker/Dockerfile -t "$TAG" .
echo "Built $TAG"
