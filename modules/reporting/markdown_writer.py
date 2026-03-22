"""Writes UTF-8 Markdown files and ensures parent directories exist."""

from __future__ import annotations

from pathlib import Path


def write_markdown(path: Path, body: str) -> Path:
    """Write `body` to `path`, creating parents as needed. Returns `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
