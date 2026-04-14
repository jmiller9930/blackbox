"""
init_schema.py

Purpose:
Apply `schema.sql` to the RenaissanceV4 SQLite database (idempotent).

Usage:
Run from repository root with PYTHONPATH including the repo:
  PYTHONPATH=. python -m renaissance_v4.data.init_schema

Version:
v1.0

Change History:
- v1.0 Initial implementation (not in pack v1; required before ingest).
"""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.utils.db import get_connection


def main() -> None:
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    print(f"[schema] Applying schema from: {schema_path}")
    connection = get_connection()
    connection.executescript(sql)
    connection.commit()
    print("[schema] Schema apply completed successfully")


if __name__ == "__main__":
    main()
