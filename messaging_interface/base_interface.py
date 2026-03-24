"""
Transport-agnostic messaging contract (Directive 4.6.3.3).

Adapters implement inbound/outbound; they must not contain reasoning, memory, or LLM logic.
"""

from __future__ import annotations

from typing import Any, Protocol


class BaseMessagingInterface(Protocol):
    """Minimal surface: receive raw user text; emit transport-formatted reply."""

    def receive_message(self, raw_text: str, *, display_name: str | None = None) -> dict[str, Any]:
        """Return dispatcher payload (kind + data) from normalized input path."""
        ...

    def send_message(self, payload: dict[str, Any], *, display_name: str | None = None) -> str:
        """Format payload for this transport (Telegram text, Slack mrkdwn, etc.)."""
        ...
