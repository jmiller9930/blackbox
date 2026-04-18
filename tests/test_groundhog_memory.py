"""Groundhog memory bundle — executable continuity across replays."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory import groundhog_memory as gm


@pytest.fixture
def gh_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "groundhog_memory_bundle.json"
    monkeypatch.setattr(gm, "groundhog_bundle_path", lambda: p)
    return p


def test_resolve_explicit_wins(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_GROUNDHOG_BUNDLE", "1")
    gh_path.write_text(
        json.dumps(
            {
                "schema": "pattern_game_memory_bundle_v1",
                "apply": {"atr_stop_mult": 1.0, "atr_target_mult": 2.0},
            }
        ),
        encoding="utf-8",
    )
    out = gm.resolve_memory_bundle_for_scenario(
        {"skip_groundhog_bundle": False},
        explicit_path="/tmp/explicit.json",
    )
    assert out == "/tmp/explicit.json"


def test_skip_groundhog(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_GROUNDHOG_BUNDLE", "1")
    gh_path.write_text(
        json.dumps(
            {
                "schema": "pattern_game_memory_bundle_v1",
                "apply": {"atr_stop_mult": 1.0, "atr_target_mult": 2.0},
            }
        ),
        encoding="utf-8",
    )
    out = gm.resolve_memory_bundle_for_scenario(
        {"skip_groundhog_bundle": True},
        explicit_path=None,
    )
    assert out is None


def test_env_merge_when_file_exists(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_GROUNDHOG_BUNDLE", "1")
    gh_path.write_text(
        json.dumps(
            {
                "schema": "pattern_game_memory_bundle_v1",
                "apply": {"atr_stop_mult": 1.5, "atr_target_mult": 3.0},
            }
        ),
        encoding="utf-8",
    )
    out = gm.resolve_memory_bundle_for_scenario({}, explicit_path=None)
    assert out == str(gh_path)


def test_env_off_no_merge(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATTERN_GAME_GROUNDHOG_BUNDLE", raising=False)
    gh_path.write_text(
        json.dumps(
            {
                "schema": "pattern_game_memory_bundle_v1",
                "apply": {"atr_stop_mult": 1.0, "atr_target_mult": 2.0},
            }
        ),
        encoding="utf-8",
    )
    out = gm.resolve_memory_bundle_for_scenario({}, explicit_path=None)
    assert out is None


def test_write_roundtrip(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_GROUNDHOG_BUNDLE", "1")
    p = gm.write_groundhog_bundle(
        atr_stop_mult=2.0,
        atr_target_mult=4.0,
        from_run_id="run-abc",
        note="promoted after batch",
    )
    assert p == gh_path
    raw = json.loads(gh_path.read_text(encoding="utf-8"))
    assert raw["apply"]["atr_stop_mult"] == 2.0
    assert raw["from_run_id"] == "run-abc"
