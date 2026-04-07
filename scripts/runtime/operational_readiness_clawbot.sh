#!/usr/bin/env bash
# Operational readiness checks on clawbot (run from ~/blackbox after git pull).
# Does NOT start Anna/sequential daemons — use with operator-provided paths and systemd/cron.
set -euo pipefail

BASE="${BASE_URL:-https://127.0.0.1}"
REPO="${BLACKBOX_REPO_ROOT:-$HOME/blackbox}"

echo "=== BLACK BOX operational readiness (clawbot) ==="
echo "BASE_URL=$BASE  REPO=$REPO"
echo

echo "--- docker compose (UIUX.Web) ---"
if [[ -d "$REPO/UIUX.Web" ]]; then
  (cd "$REPO/UIUX.Web" && docker compose ps 2>/dev/null || true)
  echo "(expect **pyth-sse-ingest** Up — Hermes SSE → market_ticks; **pyth-stream** reads DB for probe JSON)"
else
  echo "skip: $REPO/UIUX.Web not found"
fi
echo

echo "--- API runtime status ---"
curl -skS "$BASE/api/v1/runtime/status" | head -c 1200 || echo "FAIL"
echo
echo

echo "--- dashboard bundle (sequential.ui_state excerpt) ---"
curl -skS "$BASE/api/v1/dashboard/bundle" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('sequential') or {}; print('sequential keys:', list(s.keys())[:12]); print('ui_state:', s.get('ui_state')); print('reason:', s.get('reason_code'))" 2>/dev/null || curl -skS "$BASE/api/v1/dashboard/bundle" | head -c 800
echo
echo

echo "--- sequential-learning control status ---"
curl -skS "$BASE/api/v1/sequential-learning/control/status" | head -c 2000 || echo "FAIL"
echo
echo

echo "--- wallet status (truth: keypair + RPC in api container env) ---"
curl -skS "$BASE/api/v1/wallet/status" | head -c 2000 || echo "FAIL"
echo
echo

echo "--- context engine ---"
curl -skS "$BASE/api/v1/context-engine/status" | head -c 800 || echo "FAIL"
echo
echo

LEDGER="${BLACKBOX_EXECUTION_LEDGER_PATH:-}"
if [[ -n "$LEDGER" && -f "$LEDGER" ]]; then
  echo "--- execution ledger row counts (BLACKBOX_EXECUTION_LEDGER_PATH=$LEDGER) ---"
  sqlite3 "$LEDGER" "SELECT mode, COUNT(*) FROM execution_ledger GROUP BY mode;" 2>/dev/null || echo "sqlite3 failed or schema differs"
else
  echo "--- execution ledger: set BLACKBOX_EXECUTION_LEDGER_PATH to a host SQLite file to count rows ---"
fi

echo
echo "Done. For RUNNING + ticks: POST /api/v1/sequential-learning/start with valid paths, then /tick."
echo "Anna paper + learning proof: run operator-approved daemons; see docs/runtime/execution_context.md"
