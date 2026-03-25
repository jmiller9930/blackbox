#!/usr/bin/env python3
"""
Operator helper — Slack channel listen without @ (directive: remove @ requirement).

Sets channels.slack.dangerouslyAllowNameMatching=true and adds per-channel
requireMention=false for #blackbox_lab name variants so OpenClaw does not skip
messages with reason \"no-mention\" (see prepareSlackMessage).

Run on the gateway host (e.g. clawbot) after backing up ~/.openclaw/openclaw.json:

  python3 ~/blackbox/scripts/openclaw/configure_slack_lab_channel_listen.py

Does NOT change Anna routing, persona enforcement, or send mechanics.

Slack app must still subscribe to message events (e.g. message.channels) in the
Slack API dashboard — this script only updates OpenClaw config.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

CONFIG = Path.home() / ".openclaw" / "openclaw.json"
# Name variants (need dangerouslyAllowNameMatching). ID is authoritative for private channels.
LAB_CHANNEL_ID = "C0ANSPTH552"
LAB_KEYS = ("blackbox_lab", "blackbox-lab", "#blackbox_lab", "#blackbox-lab")


def main() -> int:
    if not CONFIG.is_file():
        print("missing", CONFIG, file=sys.stderr)
        return 1
    raw = CONFIG.read_text(encoding="utf-8")
    bak = CONFIG.with_suffix(".json.bak.slack_listen")
    shutil.copy2(CONFIG, bak)
    d = json.loads(raw)
    slack = d.setdefault("channels", {}).setdefault("slack", {})
    slack["dangerouslyAllowNameMatching"] = True
    ch = slack.setdefault("channels", {})
    ch[LAB_CHANNEL_ID] = {"requireMention": False}
    for key in LAB_KEYS:
        ch[key] = {"requireMention": False}
    CONFIG.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print("ok wrote", CONFIG, "backup", bak)
    print("channels.slack.channels keys:", sorted(ch.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
