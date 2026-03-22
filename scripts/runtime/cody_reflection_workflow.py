#!/usr/bin/env python3
"""
Phase 2.1 — Lightweight reflection over recent tasks (deterministic; no ML).

Reads bounded tasks from SQLite, parses description JSON for outcome + alert linkage,
emits structured JSON. Optional: store summary as a new tasks row (no schema change).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_/-]+")


def _keywords(text: str, top: int = 8) -> list[str]:
    if not text:
        return []
    c = Counter(w.lower() for w in _WORD_RE.findall(text) if len(w) > 2)
    return [w for w, _ in c.most_common(top)]


def _parse_task_row(row: tuple) -> dict:
    task_id, title, desc, state, created_at, updated_at = row
    title = title or ""
    parsed: dict = {}
    raw_ok = False
    if desc and str(desc).strip():
        try:
            parsed = json.loads(desc)
            raw_ok = True
        except json.JSONDecodeError:
            parsed = {"_non_json_preview": str(desc)[:400]}

    outcome = parsed.get("outcome") if isinstance(parsed, dict) else None
    coord = parsed.get("coordination") if isinstance(parsed, dict) else None
    ost = None
    validated_by = None
    if isinstance(outcome, dict):
        ost = outcome.get("status")
        validated_by = outcome.get("validated_by")
    alert_id = None
    if isinstance(coord, dict):
        alert_id = coord.get("responded_to_alert_id")

    blob = json.dumps(parsed, ensure_ascii=False) if parsed else ""
    return {
        "task_id": task_id,
        "title": title,
        "state": state,
        "created_at": created_at,
        "updated_at": updated_at,
        "description_is_json": raw_ok,
        "outcome_status": ost,
        "validated_by": validated_by,
        "responded_to_alert_id": alert_id,
        "keywords": _keywords(title + " " + blob),
    }


def _patterns(bucket: list[dict], label: str) -> dict:
    titles = [b["title"] for b in bucket if b.get("title")]
    kws: Counter[str] = Counter()
    for b in bucket:
        for k in b.get("keywords") or []:
            kws[k] += 1
    return {
        "label": label,
        "count": len(bucket),
        "sample_task_ids": [b["task_id"] for b in bucket[:5]],
        "sample_titles": titles[:5],
        "recurring_keywords": [w for w, _ in kws.most_common(6)],
    }


def _recommendations(
    success: list[dict],
    failure: list[dict],
    unknown: list[dict],
    total: int,
) -> list[str]:
    out: list[str] = []
    if unknown:
        out.append(
            f"Address {len(unknown)} task(s) with missing or unknown outcomes — "
            "extend DATA validation beyond disk heuristics or add human review."
        )
    if failure:
        out.append(
            f"Review {len(failure)} failed outcome(s) for recurring causes "
            "(check notes in task JSON and related alerts)."
        )
    if success and not failure and len(unknown) <= total // 2:
        out.append(
            "Success outcomes dominate; keep recording validated_by and notes for auditability."
        )
    if total == 0:
        out.append("No tasks in scope — run coordination or plan workflows to build history.")
    if not out:
        out.append(
            "Continue outcome recording after each coordination cycle to deepen reflection signal."
        )
    return out


def _confidence_notes(n_tasks: int, n_json: int) -> str:
    return (
        f"Deterministic, non-ML summary over {n_tasks} task row(s); "
        f"{n_json} had parseable JSON descriptions. "
        "Keyword themes are heuristic; not predictive."
    )


def build_reflection(
    rows: list[tuple],
    db_path: Path,
    limit: int,
) -> dict:
    summaries = [_parse_task_row(r) for r in rows]
    success = [s for s in summaries if s.get("outcome_status") == "success"]
    failure = [s for s in summaries if s.get("outcome_status") == "failure"]
    unknown = [
        s
        for s in summaries
        if s.get("outcome_status") not in ("success", "failure")
    ]

    ts_min = min((s["updated_at"] for s in summaries if s.get("updated_at")), default=None)
    ts_max = max((s["updated_at"] for s in summaries if s.get("updated_at")), default=None)

    review_scope = {
        "task_limit": limit,
        "tasks_fetched": len(summaries),
        "database": str(db_path),
        "updated_at_range": {"min": ts_min, "max": ts_max},
    }

    return {
        "schema_version": 1,
        "kind": "cody_reflection_summary_v1",
        "review_scope": review_scope,
        "tasks_reviewed": summaries,
        "successful_patterns": _patterns(success, "success"),
        "failed_patterns": _patterns(failure, "failure"),
        "unknown_patterns": _patterns(unknown, "unknown_or_missing_outcome"),
        "recommended_improvements": _recommendations(success, failure, unknown, len(summaries)),
        "confidence_notes": _confidence_notes(
            len(summaries),
            sum(1 for s in summaries if s.get("description_is_json")),
        ),
    }


def run(
    db_path: Path,
    limit: int,
    *,
    store: bool,
) -> int:
    root = repo_root()
    conn = connect(db_path)
    try:
        ensure_schema(conn, root)
        seed_agents(conn)
    except Exception as e:
        print(f"schema/seed error: {e}", file=sys.stderr)
        return 2

    rows = conn.execute(
        """
        SELECT id, title, description, state, created_at, updated_at
        FROM tasks
        WHERE title IS NULL OR title NOT LIKE '[Reflection]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    reflection = build_reflection(rows, db_path, limit)
    reflection["generated_at"] = _utc_now()

    out = {"reflection": reflection, "stored_task_id": None}
    if store:
        tid = str(uuid.uuid4())
        now = _utc_now()
        title = f"[Reflection] Last {len(rows)} task(s) @ {now[:19]}"
        desc = json.dumps(reflection, ensure_ascii=False, indent=2)
        conn.execute(
            """
            INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, "main", title, desc, "completed", "low", now, now),
        )
        conn.commit()
        out["stored_task_id"] = tid

    conn.close()

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 2.1 — reflection summary over recent tasks (no ML)",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--limit",
        type=int,
        default=30,
        metavar="N",
        help="Max recent tasks to review (default: 30)",
    )
    p.add_argument(
        "--store",
        action="store_true",
        help="Persist reflection JSON as a new completed task row",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(db, max(1, args.limit), store=args.store)


if __name__ == "__main__":
    raise SystemExit(main())
