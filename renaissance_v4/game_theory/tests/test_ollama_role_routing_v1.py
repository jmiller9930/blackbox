"""Role-based Ollama routing — Barney/Ask DATA vs Student vs System Agent vs DeepSeek escalation."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.ollama_role_routing_v1 import (
    deepseek_escalation_ollama_base_url,
    deepseek_escalation_ollama_model,
    ollama_role_routing_snapshot_v1,
    pml_lightweight_ollama_base_url,
    pml_lightweight_ollama_model,
    student_ollama_base_url_v1,
    system_agent_ollama_base_url,
    system_agent_ollama_model_fallback,
    system_agent_ollama_model_primary,
)


def test_pml_lightweight_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PML_LIGHTWEIGHT_OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("PML_LIGHTWEIGHT_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert pml_lightweight_ollama_base_url() == "http://172.20.2.230:11434"
    assert pml_lightweight_ollama_model() == "qwen2.5:7b"


def test_pml_lightweight_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PML_LIGHTWEIGHT_OLLAMA_BASE_URL", "http://10.0.0.1:11434")
    monkeypatch.setenv("PML_LIGHTWEIGHT_OLLAMA_MODEL", "qwen2.5:0.5b")
    assert pml_lightweight_ollama_base_url() == "http://10.0.0.1:11434"
    assert pml_lightweight_ollama_model() == "qwen2.5:0.5b"


def test_system_agent_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYSTEM_AGENT_OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("SYSTEM_AGENT_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("SYSTEM_AGENT_OLLAMA_MODEL_FALLBACK", raising=False)
    assert system_agent_ollama_base_url() == "http://172.20.2.230:11434"
    assert system_agent_ollama_model_primary() == "qwen2.5:7b"
    assert system_agent_ollama_model_fallback() == "qwen2.5-coder:7b"


def test_student_default_lab_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STUDENT_OLLAMA_BASE_URL", raising=False)
    assert student_ollama_base_url_v1() == "http://172.20.2.230:11434"


def test_student_base_prefers_student_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDENT_OLLAMA_BASE_URL", "http://student-only.example:11434")
    monkeypatch.setenv("PML_LIGHTWEIGHT_OLLAMA_BASE_URL", "http://pml.example:11434")
    assert student_ollama_base_url_v1() == "http://student-only.example:11434"


def test_deepseek_escalation_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_ESCALATION_OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_ESCALATION_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("PML_LIGHTWEIGHT_OLLAMA_BASE_URL", raising=False)
    assert deepseek_escalation_ollama_model() == "deepseek-r1:14b"
    assert deepseek_escalation_ollama_base_url() == "http://172.20.2.230:11434"


def test_snapshot_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PML_LIGHTWEIGHT_OLLAMA_BASE_URL", raising=False)
    snap = ollama_role_routing_snapshot_v1()
    assert snap.get("schema") == "ollama_role_routing_snapshot_v1"
    assert snap["pml_lightweight"]["ollama_model"] == "qwen2.5:7b"
    assert snap["system_agent"]["ollama_model_primary"] == "qwen2.5:7b"
