"""Apply bridge schema if needed; seed agents for tasks FK."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def ensure_schema(conn: sqlite3.Connection, repo_root: Path) -> None:
    for name in ("schema_phase1_5.sql", "schema_phase1_6.sql"):
        p = repo_root / "data" / "sqlite" / name
        if not p.is_file():
            raise FileNotFoundError(p)
        conn.executescript(p.read_text(encoding="utf-8"))
    conn.commit()


def seed_agents(conn: sqlite3.Connection) -> None:
    # id "main" is legacy primary key for Cody (engineer); kept for existing tasks / FKs.
    conn.execute(
        "INSERT OR IGNORE INTO agents (id, name, role, status) VALUES (?, ?, ?, ?)",
        ("main", "Cody", "engineer-planner-builder", "active"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO agents (id, name, role, status) VALUES (?, ?, ?, ?)",
        ("data", "DATA", "integrity-operator", "active"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO agents (id, name, role, status) VALUES (?, ?, ?, ?)",
        ("anna", "Anna", "trading-analyst", "active"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO agents (id, name, role, status) VALUES (?, ?, ?, ?)",
        ("mia", "Mia", "reserved", "inactive"),
    )
    conn.commit()
