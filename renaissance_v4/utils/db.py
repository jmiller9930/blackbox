"""
db.py

Purpose:
Provide SQLite connection helpers for RenaissanceV4.

**Optional env:** ``RENAISSANCE_V4_DB_PATH`` — path to ``*.sqlite3`` used instead of
``renaissance_v4/data/renaissance_v4.sqlite3``. Set in the **parent process before**
importing modules that open the DB (e.g. ``scripts/verify_student_loop_sr1.py`` for
deterministic SR-1 fixtures).

Usage:
Imported by database setup, ingestion, validation, and replay modules.

Version:
v1.1

Change History:
- v1.0 Initial Phase 1 implementation.
- v1.1 ``RENAISSANCE_V4_DB_PATH`` override for pinned lab fixtures.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_RENAISSANCE_V4_ROOT = Path(__file__).resolve().parent.parent
# Overridden for deterministic CI/lab fixtures (e.g. Student SR-1 proof). Set before importing replay.
_override = (os.environ.get("RENAISSANCE_V4_DB_PATH") or "").strip()
DB_PATH = Path(_override).expanduser().resolve() if _override else (_RENAISSANCE_V4_ROOT / "data" / "renaissance_v4.sqlite3")


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
