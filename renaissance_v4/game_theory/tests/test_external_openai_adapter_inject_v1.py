"""Host envfile inject: can succeed if the file appears after the first miss (regression guard)."""

from __future__ import annotations

import pytest

import renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 as adapter_mod
from renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 import _get_api_key


def test_inject_retried_when_secrets_file_created_after_first_key_lookup(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = tmp_path / "openai.env"
    monkeypatch.setenv("BLACKBOX_OPENAI_ENV_FILE", str(p))
    monkeypatch.setattr(adapter_mod, "_INJECTED_HOST_OPENAI_FILE", False)
    assert _get_api_key("OPENAI_API_KEY") is None
    p.write_text("export OPENAI_API_KEY='sk-late-file-appears-test-xyzabc'\n", encoding="utf-8")
    assert _get_api_key("OPENAI_API_KEY") is not None
