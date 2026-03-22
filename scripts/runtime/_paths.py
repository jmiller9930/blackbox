"""Resolve repo root and default SQLite path for runtime workflows."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_sqlite_path() -> Path:
    env = os.environ.get("BLACKBOX_SQLITE_PATH")
    if env:
        return Path(env).expanduser()
    return repo_root() / "data" / "sqlite" / "blackbox.db"
