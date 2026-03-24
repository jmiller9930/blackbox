"""Directive 4.6.3 — factual bypass, no template leakage in Telegram-facing Anna output."""
from __future__ import annotations

import sys
from pathlib import Path

import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "runtime"))

from anna_modules.analysis import build_analysis
from telegram_interface.message_router import route_message
from telegram_interface.agent_dispatcher import dispatch
from telegram_interface.response_formatter import format_response


def _minimal_ctx():
    return dict(
        market=None,
        market_err=None,
        ctx=None,
        ctx_err=None,
        trend=None,
        trend_err=None,
        policy=None,
        policy_err=None,
        use_snapshot=False,
        use_ctx=False,
        use_trend=False,
        use_policy=False,
    )


def test_what_day_bypass_no_market_commentary_template() -> None:
    a = build_analysis("What day is it?", **_minimal_ctx())
    assert a.get("human_intent", {}).get("bypass") == "datetime"
    interp = a.get("interpretation") or {}
    summ = str(interp.get("summary", ""))
    assert "general market commentary" not in summ.lower()
    assert "guardrail" not in summ.lower()
    assert re.search(r"\d{4}-\d{2}-\d{2}", summ), summ


def test_telegram_anna_no_caution_flags_no_registry_notes() -> None:
    r = route_message("What day is it?")
    assert r.agent == "anna"
    payload = dispatch(r, display_name="Sam")
    out = format_response(payload, user_display_name="Sam")
    assert "anna_analysis_v1" not in out.lower()
    assert "advisory only; no execution" not in out.lower()
    assert "registry" not in out.lower()
    assert "guardrail" not in out.lower()
    assert "Risk read" not in out


def test_exit_question_not_factual_bypass() -> None:
    a = build_analysis("When should I scale out of this winner?", **_minimal_ctx())
    assert a.get("human_intent", {}).get("topic") == "exit_logic"
    assert a.get("human_intent", {}).get("bypass") is None
    assert a.get("strategy_playbook_applied") is True
    interp = a.get("interpretation") or {}
    summary = str(interp.get("summary") or "")
    signals = interp.get("signals") or []
    assert "momentum" in summary.lower() or "partial" in summary.lower()
    assert "playbook:exit_timing" in signals


def test_formatter_filters_internal_notes() -> None:
    from telegram_interface.response_formatter import _telegram_safe_anna_notes

    raw = [
        "Snapshot OK",
        "No registry-backed concepts matched trader input (read-only detection).",
        "guardrail policy missing",
    ]
    safe = _telegram_safe_anna_notes(raw)
    assert "Snapshot OK" in safe
    assert not any("registry" in x.lower() for x in safe)
    assert not any("guardrail" in x.lower() for x in safe)
