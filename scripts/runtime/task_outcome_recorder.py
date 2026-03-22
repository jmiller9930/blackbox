#!/usr/bin/env python3
"""
Phase 2.0 — Record task outcome inside tasks.description JSON (no schema change).

Merges:
  "outcome": {
    "status": "success" | "failure" | "unknown",
    "timestamp": "<ISO8601>",
    "notes": "...",
    "validated_by": "DATA" | "human"
  }

Preserves coordination.responded_to_alert_id and the rest of the payload.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root
from _task_json import load_description_json, merge_outcome, save_description_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(
    db_path: Path,
    task_id: str,
    status: str,
    notes: str,
    validated_by: str,
) -> int:
    if status not in ("success", "failure", "unknown"):
        print("status must be success | failure | unknown", file=sys.stderr)
        return 2
    if validated_by not in ("DATA", "human"):
        print("validated_by must be DATA | human", file=sys.stderr)
        return 2

    root = repo_root()
    conn = connect(db_path)
    try:
        ensure_schema(conn, root)
        seed_agents(conn)
    except Exception as e:
        print(f"schema/seed error: {e}", file=sys.stderr)
        return 3

    try:
        payload, _raw = load_description_json(conn, task_id)
    except (LookupError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 4

    now = _utc_now()
    outcome = {
        "status": status,
        "timestamp": now,
        "notes": notes,
        "validated_by": validated_by,
    }
    merged = merge_outcome(payload, outcome)
    save_description_json(conn, task_id, merged, now)
    conn.commit()
    conn.close()

    print(json.dumps({"task_id": task_id, "outcome": outcome, "merged_keys": list(merged.keys())}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Record task outcome JSON (Phase 2.0)")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--task-id", required=True)
    p.add_argument(
        "--status",
        required=True,
        choices=("success", "failure", "unknown"),
    )
    p.add_argument("--notes", default="", help="Free-text notes")
    p.add_argument(
        "--validated-by",
        default="human",
        choices=("DATA", "human"),
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(db, args.task_id, args.status, args.notes, args.validated_by)


if __name__ == "__main__":
    raise SystemExit(main())
