"""
Telegram transport: format dispatcher payloads for Telegram Bot API text (Directive 4.6.3.3).

No routing or Anna logic — delegates to existing response_formatter.

`run_telegram_bot_from_config` starts the existing polling bot (Directive 4.6.3.4).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME = _REPO_ROOT / "scripts" / "runtime"


def _ensure_runtime_path() -> None:
    r = str(_RUNTIME)
    if r not in sys.path:
        sys.path.insert(0, r)


def _ensure_repo_then_runtime_path() -> None:
    """Match `telegram_bot.py` order: [scripts/runtime, repo] so `telegram_interface` + `messaging_interface` resolve."""
    rr = str(_REPO_ROOT)
    if rr not in sys.path:
        sys.path.insert(0, rr)
    _ensure_runtime_path()


def format_telegram_reply(payload: dict[str, Any], *, user_display_name: str | None = None) -> str:
    """User-visible Telegram string for a dispatcher payload."""
    _ensure_runtime_path()
    from telegram_interface.response_formatter import format_response

    return format_response(payload, user_display_name=user_display_name)


def format_telegram_system_message(body: str, *, user_display_name: str | None = None) -> str:
    """System paths (/start, errors) — still tagged Anna surface."""
    _ensure_runtime_path()
    from telegram_interface.response_formatter import format_anna_system_message

    return format_anna_system_message(body, user_display_name=user_display_name)


def run_telegram_bot_from_config(cfg: dict[str, Any]) -> int:
    """Set TELEGRAM_BOT_TOKEN from config and start existing `telegram_bot.main` (polling)."""
    m = cfg.get("messaging") or {}
    tg = m.get("telegram") or {}
    tok = (tg.get("token") or "").strip()
    if not tok:
        raise ValueError("telegram.token missing")
    os.environ["TELEGRAM_BOT_TOKEN"] = tok
    _ensure_repo_then_runtime_path()
    from telegram_interface.telegram_bot import main

    return main()
