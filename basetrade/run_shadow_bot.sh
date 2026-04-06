#!/usr/bin/env bash
# Run Sean's trading_core bot (dumb process: npm run bot) for a fixed wall time and log everything.
# Usage: ./basetrade/run_shadow_bot.sh [seconds]
# Default: 1800 (30 minutes). Use 3600 for one hour.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TC="${ROOT}/trading_core"
DURATION="${1:-1800}"
LOGDIR="${ROOT}/basetrade/logs"
mkdir -p "${LOGDIR}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="${LOGDIR}/shadow_bot_${STAMP}.log"
META="${LOGDIR}/shadow_bot_${STAMP}.meta.json"

if [[ ! -d "${TC}" ]] || [[ ! -f "${TC}/package.json" ]]; then
  echo "error: trading_core not found at ${TC}" >&2
  exit 1
fi

cd "${TC}"
if ! command -v npm >/dev/null 2>&1; then
  echo "error: npm not on PATH" >&2
  exit 1
fi

echo "Installing deps (if needed)..." | tee -a "${LOG}"
npm install >>"${LOG}" 2>&1

echo "{\"started_utc\":\"${STAMP}\",\"duration_sec\":${DURATION},\"repo\":\"${ROOT}\",\"cmd\":\"npm run bot\",\"timeout\":\"timeout ${DURATION}\"}" > "${META}"

echo "Running: wall-clock ${DURATION}s npm run bot  (log: ${LOG})"
echo "---" | tee -a "${LOG}"
# Prefer timeout/gtimeout; else background + sleep + kill (macOS-friendly)
if command -v gtimeout >/dev/null 2>&1; then
  gtimeout "${DURATION}" npm run bot 2>&1 | tee -a "${LOG}" || true
elif command -v timeout >/dev/null 2>&1; then
  timeout "${DURATION}" npm run bot 2>&1 | tee -a "${LOG}" || true
else
  npm run bot 2>&1 | tee -a "${LOG}" &
  BOTPID=$!
  sleep "${DURATION}" || true
  kill "${BOTPID}" 2>/dev/null || true
  wait "${BOTPID}" 2>/dev/null || true
fi

echo "Done. Log: ${LOG}"
echo "Summarize: python3 ${ROOT}/basetrade/summarize_log.py ${LOG}"
