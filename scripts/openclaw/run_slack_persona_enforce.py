#!/usr/bin/env python3
"""Bridge for OpenClaw send.ts — stdin raw model text, stdout enforced Slack text."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from messaging_interface.slack_persona_enforcement import enforce_slack_outbound


def main() -> None:
    raw = sys.stdin.read()
    text, _ = enforce_slack_outbound(raw)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
