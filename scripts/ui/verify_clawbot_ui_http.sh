#!/usr/bin/env bash
# Primary-host HTTP smoke: page loads + GET /api/v1/* (no auth).
# Usage: BASE_URL=https://clawbot.a51.corp ./verify_clawbot_ui_http.sh
set -uo pipefail
BASE="${BASE_URL:-https://127.0.0.1}"
K="${CURL_INSECURE:--k}"

echo "## HTTP smoke — BASE=$BASE"
echo "| URL | code | bytes |"
echo "|-----|------|-------|"

check() {
  local path="$1"
  local url="${BASE%/}${path}"
  local code bytes
  code=$(curl -sS -o /tmp/ui_smoke_body -w "%{http_code}" $K "$url" || echo "000")
  bytes=$(wc -c </tmp/ui_smoke_body 2>/dev/null || echo 0)
  echo "| \`$path\` | $code | $bytes |"
}

# API-served HTML (nginx → api:8080)
check "/dashboard.html"
check "/dashboard"
check "/anna/sequential-learning"
check "/anna/training"
check "/anna/event-view"
check "/anna/evaluation"
check "/anna/event-dashboard"

# Static (nginx try_files) — common portal pages
for p in / /index.html /login.html /internal.html /anna.html /guide.html \
  /consumer.html /docs.html /account-settings.html /internal-plan.html /internal-users.html \
  /forgot-password.html /reset-password.html /register.html /verify-email.html \
  /docs-anna-language.html /docs-system-usage.html /docs-ui-context.html /docs-web-architecture.html; do
  check "$p"
done

echo ""
echo "## GET /api/v1/* (JSON)"
echo "| path | code |"
echo "|------|------|"

apicheck() {
  local path="$1"
  local url="${BASE%/}${path}"
  local code
  code=$(curl -sS -o /dev/null -w "%{http_code}" $K "$url" || echo "000")
  echo "| \`$path\` | $code |"
}

apicheck "/api/v1/runtime/status"
apicheck "/api/v1/agents/status"
apicheck "/api/v1/system/status"
apicheck "/api/v1/wallet/status"
apicheck "/api/v1/dashboard/bundle"
apicheck "/api/v1/sequential-learning/control/status"
apicheck "/api/v1/context-engine/status"
apicheck "/api/v1/market/pyth/status"
apicheck "/api/v1/market/pyth/recent?limit=5"
apicheck "/api/v1/anna/summary"
apicheck "/api/v1/anna/training-dashboard"
apicheck "/api/v1/anna/strategies/catalog"
apicheck "/api/v1/anna/evaluation-summary?strategy_id=test"
rm -f /tmp/ui_smoke_body
