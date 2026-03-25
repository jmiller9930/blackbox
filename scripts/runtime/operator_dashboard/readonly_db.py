"""Read-only SQLite connections for the operator dashboard (no mutations)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from learning_core.remediation_validation import assert_non_production_sqlite_path


def open_sandbox_readonly(path: Path | str) -> sqlite3.Connection:
    """
    Open sandbox DB in read-only mode. Uses URI mode=ro and PRAGMA query_only when supported.
    """
    assert_non_production_sqlite_path(path)
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"sandbox database not found: {p}")
    uri = f"file:{p}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
    except sqlite3.Error:
        pass
    return conn
