#!/usr/bin/env python3
"""Merge development_plan.md + WEB_ARCHITECTURE_CANONICAL.md into one portal document."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "UIUX.Web" / "content" / "UNIFIED_PLAN.md"
DEV = REPO / "docs" / "architect" / "development_plan.md"
WEB = REPO / "UIUX.Web" / "WEB_ARCHITECTURE_CANONICAL.md"

HEADER = """# BLACK BOX unified plan (portal)

*Single document for the internal portal: master **development plan** plus **web UI architecture**.*

**Generated — do not edit.** Regenerate after changing either source:

`python3 scripts/build_unified_portal_plan.py`

---

"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    dev_text = DEV.read_text(encoding="utf-8")
    web_text = WEB.read_text(encoding="utf-8")
    body = (
        HEADER
        + "# Part 1 — Development plan\n\n"
        + f"*Source: `{DEV.relative_to(REPO)}`*\n\n"
        + dev_text
        + "\n\n---\n\n# Part 2 — Web UI architecture (canonical)\n\n"
        + f"*Source: `{WEB.relative_to(REPO)}`*\n\n"
        + web_text
        + "\n"
    )
    OUT.write_text(body, encoding="utf-8")
    print(f"Wrote {OUT} ({len(body):,} bytes)")


if __name__ == "__main__":
    main()
