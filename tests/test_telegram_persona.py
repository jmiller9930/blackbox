"""Phase 4.6.x — persona tags, routing defaults, enforcement (clawbot / CI proof)."""
from __future__ import annotations

import re

import pytest

# Runtime package lives under scripts/runtime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "runtime"))

from telegram_interface.agent_dispatcher import telegram_anna_use_llm
from telegram_interface.message_router import route_message
from telegram_interface.response_formatter import (
    format_anna_system_message,
    format_response,
)


def _first_line_tag(text: str) -> str | None:
    line = (text or "").strip().split("\n", 1)[0].strip()
    m = re.match(r"^\[(Anna|DATA|Cody|Mia)(\s+—[^\]]*)?\]", line)
    return m.group(1) if m else None


@pytest.mark.parametrize(
    "q",
    [
        "what is a spread?",
        "what is a margin call?",
        "Do you understand the system rules?",
    ],
)
def test_general_education_routes_to_anna(q: str) -> None:
    r = route_message(q)
    assert r.agent == "anna", f"expected anna for {q!r}, got {r.agent}"


def test_format_response_unknown_kind_falls_back_to_tagged_anna() -> None:
    out = format_response({"kind": "bogus"}, user_display_name="John")
    assert _first_line_tag(out) == "Anna"
    assert "John" in out
    assert "re-evaluate" in out.lower() or "closer look" in out.lower()


def test_format_response_enforces_tag_when_missing() -> None:
    # Direct call cannot bypass enforcement from format_response; simulate via public contract:
    # all payloads go through branches — unknown kind hits Anna fallback.
    out = format_response({}, user_display_name=None)
    assert _first_line_tag(out) == "Anna"


def test_format_anna_system_message_is_tagged() -> None:
    out = format_anna_system_message("Hello from /start.", user_display_name="John")
    assert out.startswith("[Anna — Trading Analyst]")
    assert "Role: Anna" not in out
    assert "John" in out or "Hello" in out


def test_telegram_anna_use_llm_env_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Telegram path uses explicit LOM resolution: TELEGRAM override, then ANNA_USE_LLM, default on."""
    monkeypatch.delenv("ANNA_TELEGRAM_USE_LLM", raising=False)
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    assert telegram_anna_use_llm() is False
    monkeypatch.setenv("ANNA_TELEGRAM_USE_LLM", "1")
    assert telegram_anna_use_llm() is True
    monkeypatch.delenv("ANNA_TELEGRAM_USE_LLM", raising=False)
    monkeypatch.delenv("ANNA_USE_LLM", raising=False)
    assert telegram_anna_use_llm() is True


def test_all_kinds_emit_first_line_persona() -> None:
    kinds = [
        ({"kind": "error", "message": "x"}, "Anna"),
        ({"kind": "anna", "data": {}}, "Anna"),
        ({"kind": "cody", "reply": "x"}, "Cody"),
        ({"kind": "identity", "intent": "help"}, "Anna"),
        (
            {
                "kind": "data",
                "data_mode": "status",
                "status_text": "ok",
            },
            "DATA",
        ),
        ({"kind": "mia", "user_text": "hi"}, "Mia"),
    ]
    for payload, want in kinds:
        out = format_response(payload, user_display_name="Test")
        assert _first_line_tag(out) == want, payload
