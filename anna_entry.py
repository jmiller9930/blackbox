#!/usr/bin/env python3
"""
Directive 4.6.3.4.C — CLI bridge: OpenClaw calls `python3 anna_entry.py "<user message>"`.

Reuses existing Anna dispatch + Telegram formatter output (same as messaging Slack adapter).
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def main() -> None:
    if len(sys.argv) < 2:
        print("", flush=True)
        sys.exit(2)
    msg = sys.argv[1]
    from messaging_interface.slack_architect_diagnostics import emit_slack_architect_block
    from messaging_interface.slack_persona_enforcement import ANNA_SLACK_STATUS, SLACK_AGENT_PREFIX
    from messaging_interface.pipeline import run_dispatch_pipeline
    from messaging_interface.telegram_adapter import format_telegram_reply

    fallback = False
    try:
        payload = run_dispatch_pipeline(msg, display_name=None)
        out = format_telegram_reply(payload, user_display_name=None)
    except Exception:
        fallback = True
        out = f"{SLACK_AGENT_PREFIX}\n\n{ANNA_SLACK_STATUS}"
    emit_slack_architect_block(
        layer="anna_entry_cli",
        user_text=msg,
        routing_decision="anna",
        anna_entry_py_ran=True,
        anna_entry_note="anna_entry.py subprocess (OpenClaw / shell); enforcement applied later in send path.",
        raw_before_enforcement=out,
        enforcement_rules_fired=[],
        final_slack_text=out,
        extra={"directive_4_fallback": fallback},
    )
    print(out, flush=True)


if __name__ == "__main__":
    main()
