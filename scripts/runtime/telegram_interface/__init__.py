"""
Phase 4.6 / 4.6.1 — Telegram interaction layer (routing + dispatch + formatting).

4.6.1: conversational shaping (identity intents, Answer→Expand→Guide→Offer, no raw JSON).
4.6.2: @anna / @data / @mia / @cody routing; [Anna]/[DATA]/[Mia]/[Cody] labels; DATA status + Cody stub.

No execution plane; no secrets in repo. Token via TELEGRAM_BOT_TOKEN.
"""
from __future__ import annotations

from .agent_dispatcher import dispatch
from .message_router import route_message, RoutedMessage
from .response_formatter import format_anna_system_message, format_response

__all__ = [
    "RoutedMessage",
    "dispatch",
    "format_anna_system_message",
    "format_response",
    "route_message",
]
