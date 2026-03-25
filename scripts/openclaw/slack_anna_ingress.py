#!/usr/bin/env python3
"""
OpenClaw Slack ingress bridge (Directive 4.6.3.4.C.1).

- If explicit_anna_route(user text): run anna_entry.py and print RAW stdout (formatter output only).
  Outbound persona enforcement runs in OpenClaw send.ts (run_slack_persona_enforce.py).
- If input is a simple greeting (e.g. "hello"): return a deterministic single-turn system reply.
- Exit 2: not an explicit Anna request (caller continues to embedded model).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from messaging_interface.anna_slack_route import explicit_anna_route

_SIMPLE_GREETING = re.compile(r"^\s*(hello|hi|hey)\s*[.!?]*\s*$", re.IGNORECASE)


def _normalize_for_greeting_match(text: str) -> str:
    t = (text or "").strip()
    # Slack sometimes passes ordered-list/code-wrapped prompts like: "1. `hello`"
    t = re.sub(r"^\s*\d+\.\s*", "", t)
    t = t.strip()
    if t.startswith("`") and t.endswith("`") and len(t) >= 2:
        t = t[1:-1].strip()
    return t


def _system_greeting_reply(text: str) -> str | None:
    """Containment guard: avoid external-tool loops on bare greeting prompts."""
    normalized = _normalize_for_greeting_match(text)
    if not _SIMPLE_GREETING.match(normalized):
        return None
    return "[BlackBox — System Agent]\n\nHello — how can I help?"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(2)
    text = sys.argv[1]
    greet = _system_greeting_reply(text)
    if greet is not None:
        sys.stdout.write(greet + "\n")
        sys.exit(0)
    if not explicit_anna_route(text):
        sys.exit(2)
    anna_py = os.path.join(_REPO, "anna_entry.py")
    proc = subprocess.run(
        [sys.executable, anna_py, text],
        cwd=_REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )
    raw = proc.stdout or ""
    if proc.returncode == 2 and not raw.strip():
        sys.exit(2)
    sys.stdout.write(raw)
    if not raw.endswith("\n") and raw.strip():
        sys.stdout.write("\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
