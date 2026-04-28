"""Ask DATA route classifier and Ollama target mapping."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.ask_data_router_v1 import (
    ask_data_ollama_target_for_route_v1,
    classify_ask_data_route_v1,
)


def test_classify_lightweight_default() -> None:
    assert classify_ask_data_route_v1("What does PML do?") == "pml_lightweight"


def test_classify_system_agent_keywords() -> None:
    assert classify_ask_data_route_v1("Explain the memory fusion policy for this run") == "system_agent"


def test_classify_deepseek_escalation_keywords() -> None:
    assert classify_ask_data_route_v1("Prove this strategy is optimal under game theory") == "deepseek_escalation"


def test_ask_data_route_env_force(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_DATA_ROUTE", "deepseek_escalation")
    assert classify_ask_data_route_v1("hello") == "deepseek_escalation"
    monkeypatch.delenv("ASK_DATA_ROUTE", raising=False)


def test_ask_data_ollama_target_for_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PML_LIGHTWEIGHT_OLLAMA_BASE_URL", "http://h1:11434")
    monkeypatch.setenv("PML_LIGHTWEIGHT_OLLAMA_MODEL", "m1")
    monkeypatch.setenv("SYSTEM_AGENT_OLLAMA_BASE_URL", "http://h2:11434")
    monkeypatch.setenv("SYSTEM_AGENT_OLLAMA_MODEL", "m2")
    monkeypatch.setenv("DEEPSEEK_ESCALATION_OLLAMA_BASE_URL", "http://h3:11434")
    monkeypatch.setenv("DEEPSEEK_ESCALATION_OLLAMA_MODEL", "m3")
    b1, m1, _ = ask_data_ollama_target_for_route_v1("pml_lightweight")
    b2, m2, _ = ask_data_ollama_target_for_route_v1("system_agent")
    b3, m3, _ = ask_data_ollama_target_for_route_v1("deepseek_escalation")
    assert (b1, m1) == ("http://h1:11434", "m1")
    assert (b2, m2) == ("http://h2:11434", "m2")
    assert (b3, m3) == ("http://h3:11434", "m3")


def test_ask_data_ollama_target_fallback_when_deepseek_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PML_LIGHTWEIGHT_OLLAMA_BASE_URL", "http://h1:11434")
    monkeypatch.setenv("PML_LIGHTWEIGHT_OLLAMA_MODEL", "m1")
    for k in (
        "DEEPSEEK_ESCALATION_OLLAMA_BASE_URL",
        "DEEPSEEK_ESCALATION_OLLAMA_MODEL",
        "SYSTEM_AGENT_OLLAMA_BASE_URL",
        "SYSTEM_AGENT_OLLAMA_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)
    b, m, _ = ask_data_ollama_target_for_route_v1("deepseek_escalation")
    assert b == "http://172.20.2.230:11434"
    assert m == "deepseek-r1:14b"
