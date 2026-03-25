"""Directive 4.6.3.4 — architect diagnostic bundle (opt-in)."""

from __future__ import annotations

import json

import pytest

from messaging_interface import slack_architect_diagnostics as sad


def test_emit_disabled_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    sad.emit_slack_architect_block(
        layer="test",
        user_text="hi",
        routing_decision="system",
        anna_entry_py_ran=False,
        raw_before_enforcement="raw",
        enforcement_rules_fired=["prepend_identity_prefix"],
        final_slack_text="final",
    )
    err = capsys.readouterr().err
    assert err == ""


def test_emit_when_enabled_json_line(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_ARCHITECT_DIAGNOSTICS", "1")
    sad.emit_slack_architect_block(
        layer="test",
        user_text="Anna, hi",
        routing_decision="anna",
        anna_entry_py_ran=True,
        anna_entry_note="note",
        raw_before_enforcement="raw",
        enforcement_rules_fired=["prepend_anna_header"],
        final_slack_text="final",
    )
    err = capsys.readouterr().err.strip()
    row = json.loads(err)
    assert row["slack_architect_diagnostics"] is True
    assert row["layer"] == "test"
    assert row["user_text"] == "Anna, hi"
    assert row["routing_decision"] == "anna"
    assert row["anna_entry_py_ran"] is True
    assert row["enforcement_rules_fired"] == ["prepend_anna_header"]
    assert row["raw_before_enforcement"] == "raw"
    assert row["final_slack_text"] == "final"
