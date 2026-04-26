"""Reasoning Model operator tile: key resolution must match the OpenAI adapter (env + host env file)."""

from __future__ import annotations

import pytest

import renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 as adapter_mod
from renaissance_v4.game_theory.reasoning_model_operator_surface_v1 import _openai_key_configured_v1


def test_openai_key_configured_uses_host_secrets_file_like_adapter(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(adapter_mod, "_INJECTED_HOST_OPENAI_FILE", False)
    f = tmp_path / "openai.env"
    f.write_text("export OPENAI_API_KEY='sk-surface-align-test-not-real-xyz'\n", encoding="utf-8")
    monkeypatch.setenv("BLACKBOX_OPENAI_ENV_FILE", str(f))
    assert _openai_key_configured_v1({"api_key_env_var": "OPENAI_API_KEY"}) is True
