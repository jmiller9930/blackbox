"""
db.py

Purpose:
Provide SQLite connection helpers for RenaissanceV4.

Usage:
Imported by ingestion, replay, logging, and scorecard modules.

Version:
v1.0

Change History:
- v1.0 Initial implementation scaffold.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_RENAISSANCE_V4_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _RENAISSANCE_V4_ROOT / "data" / "renaissance_v4.sqlite3"


def get_connection() -> sqlite3.Connection:
    """
    Open and return a SQLite connection for the RenaissanceV4 database.
    Prints the database path for visible debugging.
    """
    print(f"[db] Opening SQLite database at: {DB_PATH.resolve()}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection
