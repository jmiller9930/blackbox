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


def default_market_data_path() -> Path:
    """Canonical Phase 5.1 market-data SQLite (separate from sandbox / blackbox.db)."""
    env = os.environ.get("BLACKBOX_MARKET_DATA_PATH")
    if env:
        return Path(env).expanduser()
    return repo_root() / "data" / "sqlite" / "market_data.db"
