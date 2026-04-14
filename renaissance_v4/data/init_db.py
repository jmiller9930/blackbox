"""
init_db.py

Purpose:
Initialize the RenaissanceV4 SQLite database using the schema.sql file.

Usage:
Run directly to create all required Phase 1 tables.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.utils.db import get_connection

_SCHEMA_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = _SCHEMA_DIR / "schema.sql"


def main() -> None:
    """
    Load the SQL schema from disk and apply it to the SQLite database.
    Prints each major action to the screen for visible validation.
    """
    print(f"[init_db] Using schema file: {SCHEMA_PATH.resolve()}")

    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"[init_db] Schema file not found: {SCHEMA_PATH}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    connection = get_connection()

    print("[init_db] Applying schema to database")
    connection.executescript(schema_sql)
    connection.commit()
    print("[init_db] Database initialization complete")


if __name__ == "__main__":
    main()
