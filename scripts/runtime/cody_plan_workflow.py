#!/usr/bin/env python3
"""Cody runtime workflow: Ollama generates a structured plan; persists one task row; prints JSON plan."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
import os
import uuid
import urllib.request
from datetime import datetime, timezone

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


PLAN_PROMPT = """You are Cody, an engineering planner. The user request is at the end.

First write a concise markdown plan using these headings (exact names):

OBJECTIVE:
STEPS:
FILES IMPACTED:
RISKS:
VALIDATION:

Then output a single JSON object in a fenced code block (```json ... ```) with keys:
"objective" (string), "steps" (array of strings), "files_impacted" (array),
"risks" (array), "validation" (array). Strings must be plain text without markdown bold.

USER REQUEST:
"""


def run(
    db_path: Path,
    user_prompt: str,
    title: str | None,
    ollama_base: str,
    model: str,
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

    full_prompt = PLAN_PROMPT + user_prompt.strip()
    raw = _generate(ollama_base, model, full_prompt)
    plan = normalize_plan(raw)
    plan["model"] = model
    plan["user_prompt"] = user_prompt.strip()

    tid = str(uuid.uuid4())
    ttitle = title or f"Plan: {user_prompt.strip()[:80]}"
    desc = json.dumps(plan, ensure_ascii=False, indent=2)
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tid, agent_id, ttitle, desc, "planned", "normal", now, now),
    )
    conn.commit()
    conn.close()

    out = {"task_id": tid, "plan": plan}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cody runtime: Ollama plan → tasks row")
    p.add_argument("prompt", nargs="?", help="User request for the patch plan")
    p.add_argument("--prompt-file", type=Path, help="Read request from file")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--ollama-base", default=None)
    p.add_argument("--model", default=None)
    args = p.parse_args(argv)

    text = args.prompt
    if args.prompt_file:
        text = args.prompt_file.read_text(encoding="utf-8")
    if not text or not str(text).strip():
        p.error("provide prompt or --prompt-file")

    db = args.db or default_sqlite_path()
    base = args.ollama_base or ollama_base_url()
    model = args.model or _ollama_model()
    return run(db, text, args.title, base, model)


if __name__ == "__main__":
    raise SystemExit(main())
