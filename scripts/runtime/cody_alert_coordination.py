#!/usr/bin/env python3
"""
Phase 1.9 — Cody coordination: read one unresolved DATA alert, produce a response plan, persist a task.

Detect → hand off → plan → persist. No automatic repair execution.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _ollama import ollama_base_url
from _paths import default_sqlite_path, repo_root
from _plan_parse import normalize_plan


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ollama_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")


def _generate(base: str, model: str, prompt: str, timeout: float = 120.0) -> str:
    url = f"{base.rstrip('/')}/api/generate"
    body = json.dumps(
        {"model": model, "prompt": prompt, "stream": False},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return (data.get("response") or "").strip()


COORD_PROMPT = """You are Cody, responding to an automated health alert raised by agent DATA in the BLACK BOX system.

DATA detected a problem. Your job is to produce an engineering response plan (investigation and remediation steps only — do not claim you executed anything).

First write a concise markdown plan using these headings (exact names):

OBJECTIVE:
STEPS:
FILES IMPACTED:
RISKS:
VALIDATION:

Then output a single JSON object in a fenced code block (```json ... ```) with keys:
"objective" (string), "steps" (array of strings), "files_impacted" (array),
"risks" (array), "validation" (array).

ALERT (JSON):
"""


def fetch_alert_row(conn, alert_id: str | None) -> tuple[str, dict]:
    """Return (alert_id, alert_dict) or raise LookupError."""
    if alert_id:
        row = conn.execute(
            """
            SELECT id, source_agent, severity, channel, message, status, created_at, acknowledged_at
            FROM alerts WHERE id = ?
            """,
            (alert_id,),
        ).fetchone()
        if not row:
            raise LookupError(f"no alert with id={alert_id}")
        keys = (
            "id",
            "source_agent",
            "severity",
            "channel",
            "message",
            "status",
            "created_at",
            "acknowledged_at",
        )
        return row[0], dict(zip(keys, row))

    row = conn.execute(
        """
        SELECT id, source_agent, severity, channel, message, status, created_at, acknowledged_at
        FROM alerts
        WHERE acknowledged_at IS NULL
          AND (
            status IS NULL
            OR TRIM(LOWER(status)) = 'open'
          )
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        raise LookupError("no unresolved alert (open + not acknowledged)")
    keys = (
        "id",
        "source_agent",
        "severity",
        "channel",
        "message",
        "status",
        "created_at",
        "acknowledged_at",
    )
    return row[0], dict(zip(keys, row))


def run(
    db_path: Path,
    alert_id: str | None,
    ollama_base: str,
    model: str,
    *,
    consume_alert: bool,
    agent_id: str = "main",
) -> int:
    root = repo_root()
    conn = connect(db_path)
    try:
        ensure_schema(conn, root)
        seed_agents(conn)
    except Exception as e:
        print(f"schema/seed error: {e}", file=sys.stderr)
        return 2

    try:
        aid, alert_snapshot = fetch_alert_row(conn, alert_id)
    except LookupError as e:
        print(str(e), file=sys.stderr)
        return 3

    alert_json = json.dumps(alert_snapshot, ensure_ascii=False, indent=2)
    full_prompt = COORD_PROMPT + "\n" + alert_json
    raw = _generate(ollama_base, model, full_prompt)
    plan = normalize_plan(raw)

    payload = {
        "coordination": {
            "kind": "cody_response_to_data_alert",
            "responded_to_alert_id": aid,
            "triggering_agent": "DATA",
            "responding_agent": "Cody",
        },
        "alert_snapshot": alert_snapshot,
        "schema_version": plan.get("schema_version", 1),
        "objective": plan.get("objective", ""),
        "steps": plan.get("steps", []),
        "files_impacted": plan.get("files_impacted", []),
        "risks": plan.get("risks", []),
        "validation": plan.get("validation", []),
        "raw_model_output": plan.get("raw_model_output", raw),
        "parse_ok": plan.get("parse_ok", False),
        "parse_method": plan.get("parse_method", "fallback"),
        "model": model,
    }

    tid = str(uuid.uuid4())
    title = f"[DATA→Cody] Response plan for alert {aid[:8]}…"
    desc = json.dumps(payload, ensure_ascii=False, indent=2)
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tid, agent_id, title, desc, "planned", "high", now, now),
    )
    if consume_alert:
        conn.execute(
            """
            UPDATE alerts SET acknowledged_at = ?, status = 'acknowledged' WHERE id = ?
            """,
            (now, aid),
        )
    conn.commit()
    conn.close()

    out = {
        "task_id": tid,
        "responded_to_alert_id": aid,
        "consume_alert": consume_alert,
        "plan": payload,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Cody coordination: one unresolved alert → structured task (Phase 1.9)",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default BLACKBOX_SQLITE_PATH or repo data/sqlite/blackbox.db)",
    )
    p.add_argument(
        "--alert-id",
        default=None,
        help="Specific alert id; default = latest open unacknowledged alert",
    )
    p.add_argument("--ollama-base", default=None)
    p.add_argument("--model", default=None)
    p.add_argument(
        "--no-consume-alert",
        action="store_true",
        help="Do not set acknowledged_at on the alert (for repeated testing)",
    )
    args = p.parse_args(argv)

    db = args.db or default_sqlite_path()
    base = args.ollama_base or ollama_base_url()
    model = args.model or _ollama_model()
    return run(
        db,
        args.alert_id,
        base,
        model,
        consume_alert=not args.no_consume_alert,
    )


if __name__ == "__main__":
    raise SystemExit(main())
