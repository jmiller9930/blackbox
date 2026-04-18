"""Agent context bundle — opt-in repo docs in Anna prompts."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.agent_context_bundle import build_context_prefix

_REPO = Path(__file__).resolve().parents[1]


def test_build_context_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANNA_CONTEXT_PROFILE", raising=False)
    assert build_context_prefix(_REPO) == ""


def test_build_context_none_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "none")
    assert build_context_prefix(_REPO) == ""


def test_build_context_includes_pattern_game_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "pattern_game")
    s = build_context_prefix(_REPO)
    assert "GAME_SPEC_INDICATOR_PATTERN_V1" in s
    assert "fusion_engine.py" in s
    assert "fuse_signal_results" in s
    assert "REPOSITORY CONTEXT" in s


def test_build_context_includes_policy_standard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "policy")
    s = build_context_prefix(_REPO)
    assert "policy_package_standard" in s
    assert "REPOSITORY CONTEXT" in s
