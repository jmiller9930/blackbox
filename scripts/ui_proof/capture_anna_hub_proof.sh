#!/usr/bin/env bash
# Capture /anna.html after dev login — Anna status panel must show /api/v1/anna/summary data.
# Run on the host that serves HTTPS (e.g. clawbot with UIUX.Web docker compose).
# Requires: Docker, image mcr.microsoft.com/playwright/python:v1.49.0-jammy (pulled on first run).
#
# Usage:
#   chmod +x scripts/ui_proof/capture_anna_hub_proof.sh
#   ./scripts/ui_proof/capture_anna_hub_proof.sh [output_dir]
#
# Env:
#   BLACKBOX_UI_HOST  default https://127.0.0.1
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="${1:-$REPO_ROOT/docs/working/ui_proof_anna_summary}"
mkdir -p "$OUT_DIR"
export BLACKBOX_UI_HOST="${BLACKBOX_UI_HOST:-https://127.0.0.1}"

docker run --rm --network host \
  -e BLACKBOX_UI_HOST \
  -v "$OUT_DIR:/out" \
  mcr.microsoft.com/playwright/python:v1.49.0-jammy \
  bash -c '
set -e
pip install -q playwright==1.49.0
playwright install chromium firefox
python3 << "PY"
import os
from playwright.sync_api import sync_playwright

HOST = os.environ.get("BLACKBOX_UI_HOST", "https://127.0.0.1").rstrip("/")

def shot(browser_factory, path: str):
    with sync_playwright() as p:
        browser = browser_factory(p)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.goto(f"{HOST}/login.html", wait_until="domcontentloaded", timeout=120000)
        page.fill("#username", "admin")
        page.fill("#password", "admin")
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle", timeout=120000)
        page.goto(f"{HOST}/anna.html", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_function(
            """() => {
              const el = document.getElementById("panel-anna-body");
              if (!el) return false;
              const t = el.innerText || "";
              return t.includes("Training feed") && (t.includes("SOL-PERP") || t.includes("market_data"));
            }""",
            timeout=120000,
        )
        page.screenshot(path=path, full_page=True)
        browser.close()

def chrome(p):
    return p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])

def ff(p):
    return p.firefox.launch(headless=True)

shot(chrome, "/out/anna_hub_chromium.png")
shot(ff, "/out/anna_hub_firefox.png")
print("ok")
PY
'
echo "Wrote: $OUT_DIR/anna_hub_chromium.png $OUT_DIR/anna_hub_firefox.png"
