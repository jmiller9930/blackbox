#!/usr/bin/env bash
# Paste Telegram bot token (from @BotFather) and write ~/.openclaw/secrets/telegram.env.
# Run on the OpenClaw gateway host (e.g. SSH to clawbot), not on your laptop.
#
# Optional env:
#   RESTART_GATEWAY=0   — do not restart openclaw-gateway.service after success
#   OPENCLAW_SECRETS_DIR — default ~/.openclaw/secrets
#
set -euo pipefail

SECRETS_DIR="${OPENCLAW_SECRETS_DIR:-$HOME/.openclaw/secrets}"
ENV_FILE="${TELEGRAM_ENV_FILE:-$SECRETS_DIR/telegram.env}"

echo "Paste your Telegram bot token from @BotFather, then press Enter."
echo "(Input is hidden.)"
read -rs TOKEN
echo

# Trim whitespace / CR from Windows paste
TOKEN="$(printf '%s' "$TOKEN" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

if [[ -z "$TOKEN" ]]; then
  echo "Empty token, aborting." >&2
  exit 1
fi

if [[ "$TOKEN" == *[![:graph:]]* ]] || [[ "$TOKEN" != *:* ]]; then
  echo "Token looks invalid (need a single line like 123456789:AAH... with no spaces)." >&2
  exit 1
fi

if [[ ${#TOKEN} -lt 40 ]]; then
  echo "Token looks too short; copy the full line from BotFather." >&2
  exit 1
fi

echo "Checking token with Telegram API..."
OUT="$(curl -sS --max-time 15 "https://api.telegram.org/bot${TOKEN}/getMe")" || {
  echo "Could not reach api.telegram.org (network or TLS issue)." >&2
  exit 1
}

if ! printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("ok") else 1)' 2>/dev/null; then
  echo "Telegram rejected this token:" >&2
  printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("description","unknown error"))' >&2
  exit 1
fi

USERNAME="$(printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("result",{}).get("username",""))')"

umask 077
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

{
  echo "# Telegram bot token for OpenClaw (written by scripts/set_telegram_bot_token.sh)"
  echo "TELEGRAM_BOT_TOKEN=${TOKEN}"
} >"$ENV_FILE"

chmod 600 "$ENV_FILE"
echo "Wrote: $ENV_FILE (chmod 600)."
echo "Telegram API OK: bot @${USERNAME}"

if [[ "${RESTART_GATEWAY:-1}" != "0" ]]; then
  if systemctl --user is-active openclaw-gateway.service &>/dev/null; then
    systemctl --user restart openclaw-gateway.service
    echo "Restarted openclaw-gateway.service"
  else
    echo "Note: openclaw-gateway.service is not active; start it when ready."
  fi
else
  echo "Skipped gateway restart (RESTART_GATEWAY=0)."
fi

echo "Next: DM your bot in Telegram, then: node /home/jmiller/openclaw/dist/index.js pairing list telegram"
