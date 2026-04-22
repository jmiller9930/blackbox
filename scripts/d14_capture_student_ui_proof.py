#!/usr/bin/env python3
"""Headless Playwright: L1 row → L2 carousel → L3 deep dive screenshots (local Flask :8765)."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "renaissance_v4/game_theory/docs/proof/d14_gc/screenshots"


def main() -> None:
    base = "http://127.0.0.1:8765"
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1100})
        page.goto(base + "/?d14proof=1", wait_until="domcontentloaded")
        page.locator("#pgStudentTriangleDock summary").click()
        page.wait_for_timeout(1200)
        page.locator("tr[data-run-row]").first.click()
        page.wait_for_selector("text=Trade carousel", timeout=20000)
        page.screenshot(path=str(OUT / "d14_proof_l2_summary_and_carousel.png"), full_page=False)
        page.locator(".pg-student-d11-slice[data-did]").first.click()
        page.wait_for_selector("text=Trade deep dive", timeout=20000)
        page.screenshot(path=str(OUT / "d14_proof_l3_deep_dive.png"), full_page=False)
        browser.close()
    print("Wrote", OUT / "d14_proof_l2_summary_and_carousel.png")
    print("Wrote", OUT / "d14_proof_l3_deep_dive.png")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("error:", e, file=sys.stderr)
        sys.exit(1)
