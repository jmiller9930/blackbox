"""
init_schema.py

Purpose:
Backward-compatible alias for Phase 1 database initialization.

Usage:
Prefer: python -m renaissance_v4.data.init_db
"""

from __future__ import annotations

from renaissance_v4.data.init_db import main

if __name__ == "__main__":
    main()
