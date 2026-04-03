"""Anna training internal LLM cross-check (no live Ollama in CI)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_RT = ROOT / "scripts" / "runtime"
if str(_RT) not in sys.path:
    sys.path.insert(0, str(_RT))

from modules.anna_training.llm_cross_check import (  # noqa: E402
    build_cross_check_prompt,
    parse_cross_check_verdict,
    run_llm_cross_check,
    training_llm_enabled,
)


def test_training_llm_enabled_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANNA_USE_LLM", raising=False)
    assert training_llm_enabled() is True
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    assert training_llm_enabled() is False


def test_parse_cross_check_verdict() -> None:
    assert parse_cross_check_verdict("VERDICT: PASS\nok") == "PASS"
    assert parse_cross_check_verdict("verdict: review\nx") == "REVIEW"
    assert parse_cross_check_verdict("no verdict here") is None


def test_build_cross_check_prompt_includes_draft() -> None:
    p = build_cross_check_prompt("hello claim", supporting_context="ctx")
    assert "hello claim" in p
    assert "ctx" in p


def test_run_llm_cross_check_skips_when_llm_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    out = run_llm_cross_check("draft")
    assert out["skipped"] is True
    assert out["llm_called"] is False


def test_run_llm_cross_check_uses_patched_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_USE_LLM", "1")
    from llm.local_llm_client import LlmResult

    def fake_generate(prompt: str, *, base_url: str, model=None, timeout: float = 120.0):
        assert "DRAFT TO CROSS-CHECK" in prompt
        return LlmResult(text="VERDICT: REVIEW\nCheck the spread assumption.\n", model="stub", error=None)

    monkeypatch.setattr("llm.local_llm_client.ollama_generate", fake_generate)

    out = run_llm_cross_check("My draft", supporting_context="numbers: x=1")
    assert out["ok"] is True
    assert out["verdict"] == "REVIEW"
    assert out["skipped"] is False
    assert "spread" in (out.get("raw_text") or "")


def test_run_llm_cross_check_propagates_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_USE_LLM", "1")
    from llm.local_llm_client import LlmResult

    def boom(prompt: str, *, base_url: str, model=None, timeout: float = 120.0):
        return LlmResult(text="", model="stub", error="connection refused")

    monkeypatch.setattr("llm.local_llm_client.ollama_generate", boom)

    out = run_llm_cross_check("draft")
    assert out["ok"] is False
    assert out["error"] == "connection refused"
