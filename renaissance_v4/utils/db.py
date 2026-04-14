"""
db.py

Purpose:
Provide SQLite connection helpers for RenaissanceV4.

Usage:
Imported by database setup, ingestion, validation, and replay modules.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_RENAISSANCE_V4_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _RENAISSANCE_V4_ROOT / "data" / "renaissance_v4.sqlite3"


def get_connection() -> sqlite3.Connection:
    """
    Open a SQLite connection to the RenaissanceV4 database.
    Prints the resolved path so the operator can verify the exact file in use.
    """
    print(f"[db] Opening database at: {DB_PATH.resolve()}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection
