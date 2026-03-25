#!/usr/bin/env python3
"""Bridge for OpenClaw send.ts — stdin raw text, stdout enforced Slack text.

Set SLACK_PERSONA_ROUTE to ``anna`` or ``system`` (default) before send so enforcement
matches the ingress routing decision (Directive 4.6.3.4.C). Inherits process env.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from messaging_interface.slack_persona_enforcement import Route, enforce_slack_outbound


def main() -> None:
    raw = sys.stdin.read()
    r = os.environ.get("SLACK_PERSONA_ROUTE", "system")
    route: Route = "anna" if r == "anna" else "system"
    text, _ = enforce_slack_outbound(raw, route=route)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
