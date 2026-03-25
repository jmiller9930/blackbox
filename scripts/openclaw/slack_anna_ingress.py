#!/usr/bin/env python3
"""
OpenClaw Slack ingress bridge (Directive 4.6.3.4.C.1).

- If explicit_anna_route(user text): run anna_entry.py and print RAW stdout (formatter output only).
  Outbound persona enforcement runs in OpenClaw send.ts (run_slack_persona_enforce.py).
- Exit 2: not an explicit Anna request (caller continues to embedded model).
"""
from __future__ import annotations

import os
import subprocess
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from messaging_interface.anna_slack_route import explicit_anna_route


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(2)
    text = sys.argv[1]
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
