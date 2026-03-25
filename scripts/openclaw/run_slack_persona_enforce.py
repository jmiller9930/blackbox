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

from messaging_interface.slack_architect_diagnostics import emit_slack_architect_block
from messaging_interface.slack_persona_enforcement import Route, enforce_slack_outbound


def main() -> None:
    raw = sys.stdin.read()
    r = os.environ.get("SLACK_PERSONA_ROUTE", "system")
    route: Route = "anna" if r == "anna" else "system"
    text, rules = enforce_slack_outbound(raw, route=route)
    ingress = (os.environ.get("SLACK_ARCHITECT_INGRESS_USER_TEXT") or "").strip() or None
    emit_slack_architect_block(
        layer="openclaw_run_slack_persona_enforce",
        user_text=ingress,
        routing_decision=route,
        anna_entry_py_ran=None,
        anna_entry_note=(
            "Set SLACK_ARCHITECT_INGRESS_USER_TEXT in gateway env if you need user text here; "
            "anna_entry runs upstream of this subprocess."
        ),
        raw_before_enforcement=raw,
        enforcement_rules_fired=rules,
        final_slack_text=text,
    )
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
