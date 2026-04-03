"""
Shared dispatch path: route → agent_dispatcher (Directive 4.6.3.3).

Anna pipeline lives in scripts/runtime; this module only wires routing + dispatch.
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


def run_dispatch_pipeline(user_text: str, *, display_name: str | None = None) -> dict[str, Any]:
    """
    Run message_router.route_message → agent_dispatcher.dispatch.

    Transport-agnostic entry used by CLI, `anna_entry` (Slack/OpenClaw), and the Telegram bot.
    """
    _ensure_runtime_path()
    from telegram_interface.agent_dispatcher import dispatch
    from telegram_interface.message_router import route_message

    routed = route_message(user_text)
    return dispatch(routed, display_name=display_name)
