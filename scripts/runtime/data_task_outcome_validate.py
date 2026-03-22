#!/usr/bin/env python3
"""
Phase 2.0 — DATA: minimal validation for disk-related tasks; writes outcome via same JSON shape.

Heuristic: if the task text (title + description JSON) suggests a disk/df/var/log check,
runs shutil.disk_usage on /var/log or /. Otherwise records outcome status=unknown.

Does not execute remediation; evaluate/record only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root
from _task_json import load_description_json, merge_outcome, save_description_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_DISK_HINT = re.compile(
    r"disk|df\b|var/log|usage\s*%|space|filesystem",
    re.I,
)


def _task_blob(payload: dict, title: str) -> str:
    parts = [title, json.dumps(payload, ensure_ascii=False)]
    return "\n".join(parts)


def _disk_paths() -> list[Path]:
    return [Path("/var/log"), Path("/")]


def validate_disk() -> tuple[bool, str]:
    """Return (ok, notes) — ok True if all checked paths below threshold."""
    threshold_pct = 99.0
    lines: list[str] = []
    for p in _disk_paths():
        try:
            u = shutil.disk_usage(str(p))
            pct = 100.0 * (u.used / u.total) if u.total else 100.0
            ok_path = pct < threshold_pct
            lines.append(f"{p}: {pct:.1f}% used (threshold <{threshold_pct}%)")
            if not ok_path:
                return False, "; ".join(lines)
        except OSError as e:
            lines.append(f"{p}: error {e}")
            return False, "; ".join(lines)
    return True, "; ".join(lines)


def run(db_path: Path, task_id: str, *, dry_run: bool) -> int:
    root = repo_root()
    conn = connect(db_path)
    try:
        ensure_schema(conn, root)
        seed_agents(conn)
    except Exception as e:
        print(f"schema/seed error: {e}", file=sys.stderr)
        return 3

    row = conn.execute(
        "SELECT title, description FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    if not row:
        print(f"task not found: {task_id}", file=sys.stderr)
        return 4

    title, desc_raw = row[0] or "", row[1] or ""
    try:
        payload = json.loads(desc_raw) if str(desc_raw).strip() else {}
    except json.JSONDecodeError as e:
        print(f"invalid JSON in task description: {e}", file=sys.stderr)
        return 5

    blob = _task_blob(payload, str(title))
    is_diskish = bool(_DISK_HINT.search(blob))

    now = _utc_now()
    if not is_diskish:
        outcome = {
            "status": "unknown",
            "timestamp": now,
            "notes": "DATA simple validator: no disk/df/var-log keyword match; skipped automated check",
            "validated_by": "DATA",
        }
    else:
        passed, vnotes = validate_disk()
        outcome = {
            "status": "success" if passed else "failure",
            "timestamp": now,
            "notes": f"DATA disk spot-check: {vnotes}",
            "validated_by": "DATA",
        }

    if dry_run:
        print(json.dumps({"task_id": task_id, "dry_run": True, "would_write": outcome}, indent=2))
        conn.close()
        return 0

    merged = merge_outcome(payload, outcome)
    save_description_json(conn, task_id, merged, now)
    conn.commit()
    conn.close()

    alert_id = (merged.get("coordination") or {}).get("responded_to_alert_id")
    print(
        json.dumps(
            {
                "task_id": task_id,
                "responded_to_alert_id": alert_id,
                "outcome": outcome,
                "disk_related": is_diskish,
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="DATA: minimal task outcome validation (disk heuristic) — Phase 2.0",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--task-id", required=True)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print outcome only; do not write DB",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(db, args.task_id, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
