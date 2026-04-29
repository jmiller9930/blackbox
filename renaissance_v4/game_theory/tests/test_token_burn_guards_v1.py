"""Tests for optional Student Ollama token burn guards."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.token_burn_guards_v1 import (
    clamp_ollama_options_v1,
    resolve_max_packet_json_chars_v1,
    token_burn_guard_enabled_v1,
)


def test_guard_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BLACKBOX_TOKEN_BURN_GUARD", raising=False)
    monkeypatch.setenv("PATTERN_GAME_STUDENT_PROMPT_PACKET_JSON_MAX", "56000")
    assert token_burn_guard_enabled_v1() is False
    assert resolve_max_packet_json_chars_v1() == 56000
    assert clamp_ollama_options_v1({"num_predict": 2048})["num_predict"] == 2048


def test_guard_on_caps_prompt_and_predict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_TOKEN_BURN_GUARD", "1")
    monkeypatch.setenv("PATTERN_GAME_STUDENT_PROMPT_PACKET_JSON_MAX", "56000")
    monkeypatch.setenv("BLACKBOX_STUDENT_PROMPT_JSON_MAX_CEILING", "32000")
    monkeypatch.setenv("BLACKBOX_OLLAMA_NUM_PREDICT_MAX", "1536")
    assert token_burn_guard_enabled_v1() is True
    assert resolve_max_packet_json_chars_v1() == 32000
    out = clamp_ollama_options_v1({"num_predict": 2048, "temperature": 0})
    assert out["num_predict"] == 1536
    assert out["temperature"] == 0


def test_clamp_accepts_none_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_TOKEN_BURN_GUARD", "1")
    assert clamp_ollama_options_v1(None) == {}
