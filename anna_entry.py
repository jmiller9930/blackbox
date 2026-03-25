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
    from messaging_interface.slack_persona_enforcement import ANNA_SLACK_STATUS, SLACK_AGENT_PREFIX
    from messaging_interface.pipeline import run_dispatch_pipeline
    from messaging_interface.telegram_adapter import format_telegram_reply

    try:
        payload = run_dispatch_pipeline(msg, display_name=None)
        out = format_telegram_reply(payload, user_display_name=None)
    except Exception:
        out = f"{SLACK_AGENT_PREFIX}\n\n{ANNA_SLACK_STATUS}"
    print(out, flush=True)


if __name__ == "__main__":
    main()
