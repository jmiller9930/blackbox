"""_ollama.ollama_base_url — env only; no openclaw.json."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

import _ollama  # noqa: E402


def test_ollama_base_url_prefers_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://10.0.0.5:11434/")
    monkeypatch.delenv("OLLAMA_STRICT", raising=False)
    assert _ollama.ollama_base_url() == "http://10.0.0.5:11434"


def test_ollama_base_url_default_localhost(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_STRICT", raising=False)
    assert _ollama.ollama_base_url() == "http://127.0.0.1:11434"


def test_ollama_strict_requires_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_STRICT", "1")
    with pytest.raises(RuntimeError, match="OLLAMA_BASE_URL"):
        _ollama.ollama_base_url()
