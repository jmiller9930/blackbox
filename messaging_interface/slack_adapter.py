"""
Slack transport only — Bolt Socket Mode, shared Anna pipeline (Directive 4.6.3.4).

No reasoning, memory, or LLM logic here.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME = _REPO_ROOT / "scripts" / "runtime"


def _ensure_runtime_path() -> None:
    r = str(_RUNTIME)
    if r not in sys.path:
        sys.path.insert(0, r)


def slack_reply_text(payload: dict[str, Any], *, user_display_name: str | None = None) -> str:
    """Reuse Telegram formatter for identical human-readable content; Slack posts as plain text."""
    from messaging_interface.telegram_adapter import format_telegram_reply

    return format_telegram_reply(payload, user_display_name=user_display_name)


def run_slack_from_config(cfg: dict[str, Any]) -> int:
    """
    Start Slack Bolt app (Socket Mode). Blocks until process exit.

    Requires: slack-bolt, slack-sdk (see requirements.txt).
    """
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError as e:
        raise RuntimeError(
            "slack-bolt is required for Slack backend. Install: pip install slack-bolt",
        ) from e

    m = cfg.get("messaging") or {}
    sl = m.get("slack") or {}
    bot_token = (sl.get("bot_token") or "").strip()
    app_token = (sl.get("app_token") or "").strip()

    os.environ.setdefault("SLACK_BOT_TOKEN", bot_token)
    os.environ.setdefault("SLACK_APP_TOKEN", app_token)

    _ensure_runtime_path()
    from messaging_interface.pipeline import run_dispatch_pipeline

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("messaging_interface.slack")

    app = App(token=bot_token)

    @app.message(re.compile(r".+", re.DOTALL))
    def handle_message(message: dict[str, Any], say: Any) -> None:
        if message.get("bot_id") or message.get("subtype") == "message_changed":
            return
        text = (message.get("text") or "").strip()
        if not text:
            return
        user = message.get("user")
        display_name = None
        try:
            info = app.client.users_info(user=user)
            if info.get("ok"):
                prof = (info.get("user") or {}).get("profile") or {}
                display_name = (prof.get("display_name") or prof.get("real_name") or "").strip() or None
        except Exception:
            pass
        try:
            payload = run_dispatch_pipeline(text, display_name=display_name)
            out = slack_reply_text(payload, user_display_name=display_name)
            say(out)
        except Exception as e:
            log.exception("slack dispatch failed")
            say(f"[Anna — Trading Analyst]\n\nI hit a snag processing that: {e!s}")

    log.info(
        "Slack Socket Mode starting (backend=slack). "
        "OpenClaw / clawbot do not handle this process — only slack-bolt with bot + app tokens.",
    )
    handler = SocketModeHandler(app, app_token)
    handler.start()
    return 0
