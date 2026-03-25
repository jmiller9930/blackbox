"""Directive 4.6.3.4.B.2 — Slack persona enforcement (deterministic)."""

from __future__ import annotations

from messaging_interface.slack_persona_enforcement import (
    ANNA_SLACK_STATUS,
    ANNA_HEADER,
    SLACK_AGENT_PREFIX,
    enforce_slack_outbound,
)


def _assert_starts_with_prefix(text: str) -> None:
    assert text.startswith(SLACK_AGENT_PREFIX), text[:80]


def test_prompt1_is_anna_online_model_violation() -> None:
    raw = (
        "Anna is offline at the moment. How about I assist you instead? "
        "If you have any questions or need help, feel free to ask!"
    )
    out, rules = enforce_slack_outbound(raw)
    _assert_starts_with_prefix(out)
    assert "offline" not in out.lower()
    assert ANNA_SLACK_STATUS in out
    joined = "|".join(rules)
    assert "prepend_identity_prefix" in rules or "replace_anna_status" in joined


def test_prompt2_spread_no_prefix() -> None:
    raw = "Sure! A **spread** is the bid-ask difference."
    out, rules = enforce_slack_outbound(raw)
    _assert_starts_with_prefix(out)
    assert "spread" in out.lower()
    assert "[Anna" not in out


def test_prompt3_anna_what_do_you_think() -> None:
    raw = (
        "I think we should consider the risk profile here. "
        "Anna would suggest reviewing your size."
    )
    out, rules = enforce_slack_outbound(raw)
    _assert_starts_with_prefix(out)
    assert "[Anna — Trading Analyst]" not in out


def test_strip_anna_analyst_tag() -> None:
    raw = "[Anna — Trading Analyst]\n\nHello there."
    out, rules = enforce_slack_outbound(raw)
    assert "[Anna — Trading Analyst]" not in out
    _assert_starts_with_prefix(out)
    assert "strip_anna_analyst_tag" in rules


def test_impersonation() -> None:
    raw = "I'm Anna and I can help with that trade."
    out, rules = enforce_slack_outbound(raw)
    assert "I'm Anna" not in out
    assert "strip_anna_impersonation" in rules
    _assert_starts_with_prefix(out)


def test_idempotent_prefix() -> None:
    raw = f"{SLACK_AGENT_PREFIX}\n\nAlready formatted body."
    out, rules = enforce_slack_outbound(raw)
    assert out.count(SLACK_AGENT_PREFIX) == 1
    assert "identity_prefix_already_present" in rules


def test_anna_still_offline_variant() -> None:
    raw = "Anna is still offline, John. Need help?"
    out, _ = enforce_slack_outbound(raw)
    _assert_starts_with_prefix(out)
    assert "offline" not in out.lower()
    assert ANNA_SLACK_STATUS in out


def test_anna_route_keeps_header() -> None:
    raw = "Anna is offline"  # wrong claim; should be fixed
    out, _ = enforce_slack_outbound(raw, route="anna")
    assert out.startswith(ANNA_HEADER)
    assert ANNA_SLACK_STATUS in out
    assert "offline" not in out.lower()


def test_anna_route_prepends_header() -> None:
    raw = "A spread is the bid-ask difference."
    out, _ = enforce_slack_outbound(raw, route="anna")
    assert out.startswith(ANNA_HEADER)
    assert "bid-ask" in out.lower()
