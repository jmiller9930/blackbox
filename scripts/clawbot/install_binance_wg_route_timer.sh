#!/usr/bin/env bash
# Install systemd timer on clawbot so Binance API routes refresh automatically when CDN IPs drift.
#
# Usage (on clawbot, from repo):
#   sudo BLACKBOX_REPO=/home/jmiller/blackbox ./scripts/clawbot/install_binance_wg_route_timer.sh
# Default BLACKBOX_REPO=$HOME/blackbox if unset and not root's home — override if your clone path differs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="${BLACKBOX_REPO:-}"
if [[ -z "$REPO" ]]; then
  if [[ -n "${SUDO_USER:-}" ]]; then
    REPO="$(getent passwd "$SUDO_USER" | cut -d: -f6)/blackbox"
  else
    REPO="${HOME}/blackbox"
  fi
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo BLACKBOX_REPO=$REPO $0" >&2
  exit 1
fi

if [[ ! -f "$REPO/scripts/clawbot/binance_api_route_via_proton_wg.sh" ]]; then
  echo "BLACKBOX_REPO=$REPO does not look like blackbox (script missing)." >&2
  exit 1
fi

replace() {
  sed "s|__BLACKBOX_REPO__|${REPO}|g" "$1"
}

replace "$SCRIPT_DIR/systemd/binance-wg-route.service" >/etc/systemd/system/binance-wg-route.service
cp "$SCRIPT_DIR/systemd/binance-wg-route.timer" /etc/systemd/system/binance-wg-route.timer

systemctl daemon-reload
systemctl enable --now binance-wg-route.timer
systemctl start binance-wg-route.service

echo "Installed. Timer status:"
systemctl status binance-wg-route.timer --no-pager -l || true
echo ""
echo "Last service run:"
systemctl status binance-wg-route.service --no-pager -l || true
