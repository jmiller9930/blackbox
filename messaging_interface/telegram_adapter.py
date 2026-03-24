"""
Telegram transport: format dispatcher payloads for Telegram Bot API text (Directive 4.6.3.3).

No routing or Anna logic — delegates to existing response_formatter.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_RUNTIME = Path(__file__).resolve().parent.parent / "scripts" / "runtime"


def _ensure_runtime_path() -> None:
    r = str(_RUNTIME)
    if r not in sys.path:
        sys.path.insert(0, r)


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
