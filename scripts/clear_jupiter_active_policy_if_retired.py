#!/usr/bin/env python3
"""
Clear analog_meta.jupiter_active_policy when its value is not in kitchen_policy_registry_v1
runtime_policies.jupiter (e.g. retired jup_mc_test).

Requires: SQLite path to Sean/Jupiter paper DB (same as jupiter-web SQLITE_PATH / SEAN_SQLITE_PATH).

Usage:
  python3 scripts/clear_jupiter_active_policy_if_retired.py /path/to/sean_parity.db /path/to/blackbox/repo
  python3 scripts/clear_jupiter_active_policy_if_retired.py   # uses env SQLITE_PATH or SEAN_SQLITE_PATH + repo root
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def main() -> int:
    repo = _ROOT
    db_path: Path | None = None
    if len(sys.argv) >= 2 and str(sys.argv[1]).strip().endswith(".db"):
        db_path = Path(sys.argv[1]).resolve()
    if len(sys.argv) >= 3:
        repo = Path(sys.argv[2]).resolve()
    if db_path is None:
        raw = (os.environ.get("SQLITE_PATH") or os.environ.get("SEAN_SQLITE_PATH") or "").strip()
        if not raw:
            print(
                "error: pass <sean.db> [repo] or set SQLITE_PATH / SEAN_SQLITE_PATH",
                file=sys.stderr,
            )
            return 1
        db_path = Path(raw).resolve()
    if not db_path.is_file():
        print(f"error: sqlite file not found: {db_path}", file=sys.stderr)
        return 1

    from renaissance_v4.kitchen_policy_registry import runtime_policy_approved

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT v FROM analog_meta WHERE k = ?",
            ("jupiter_active_policy",),
        ).fetchone()
        cur = str(row[0] or "").strip() if row else ""
        if not cur:
            print(json.dumps({"ok": True, "changed": False, "detail": "jupiter_active_policy unset"}))
            return 0
        if runtime_policy_approved(repo, "jupiter", cur):
            print(
                json.dumps(
                    {
                        "ok": True,
                        "changed": False,
                        "active_policy": cur,
                        "detail": "still approved in kitchen_policy_registry_v1",
                    }
                )
            )
            return 0
        conn.execute(
            "DELETE FROM analog_meta WHERE k = ?",
            ("jupiter_active_policy",),
        )
        conn.commit()
        print(
            json.dumps(
                {
                    "ok": True,
                    "changed": True,
                    "cleared_policy": cur,
                    "detail": "removed — not in registry allowlist",
                }
            )
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
