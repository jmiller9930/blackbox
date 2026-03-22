"""Converts outline text into a flat list of non-empty lines for planning."""

from __future__ import annotations


def parse_outline(outline: str) -> list[str]:
    """Split `outline` on lines and return stripped non-empty entries."""
    lines = [ln.strip() for ln in outline.splitlines() if ln.strip()]
    return lines or ["(empty outline)"]
