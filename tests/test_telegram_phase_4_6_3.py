"""Phase 4.6.3 — directive routing + first-line persona tags (CI proof; mirror Telegram tests)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "runtime"))

from telegram_interface.message_router import route_message


def _first_tag(text: str) -> str | None:
    line = (text or "").strip().split("\n", 1)[0].strip()
    m = re.match(r"^\[(Anna|DATA|Cody|Mia)\]", line)
    return m.group(1) if m else None


def test_directive_routing_table() -> None:
    cases = [
        ("what is a spread?", "anna"),
        ("what is a liquidity event?", "anna"),
        ("what is a futures contract?", "anna"),
        ("@data status", "data"),
        ("@cody what can you improve?", "cody"),
    ]
    for q, want in cases:
        r = route_message(q)
        assert r.agent == want, f"{q!r} -> expected {want}, got {r.agent}"


def test_format_response_first_lines_match_directive() -> None:
    from telegram_interface.agent_dispatcher import dispatch
    from telegram_interface.response_formatter import format_response

    table = [
        ("what is a spread?", "Anna"),
        ("what is a liquidity event?", "Anna"),
        ("what is a futures contract?", "Anna"),
        ("@data status", "DATA"),
        ("@cody what can you improve?", "Cody"),
    ]
    for q, want_tag in table:
        r = route_message(q)
        payload = dispatch(r, display_name="John")
        out = format_response(payload, user_display_name="John")
        assert _first_tag(out) == want_tag, f"{q!r} -> {out[:120]!r}"
