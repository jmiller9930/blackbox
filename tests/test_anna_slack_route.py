"""Directive 4.6.3.4.C — explicit-only Anna routing."""

from __future__ import annotations

from messaging_interface.anna_slack_route import explicit_anna_route


def test_hello_not_anna() -> None:
    assert explicit_anna_route("hello") is False


def test_spread_without_anna() -> None:
    assert explicit_anna_route("what is a spread?") is False


def test_anna_comma() -> None:
    assert explicit_anna_route("Anna, what is a spread?") is True


def test_word_anna() -> None:
    assert explicit_anna_route("please ask Anna tomorrow") is True


def test_at_anna() -> None:
    assert explicit_anna_route("Hey @Anna there") is True


def test_johanna_no_false_positive() -> None:
    assert explicit_anna_route("Johanna said hi") is False
