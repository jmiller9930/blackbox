"""PATTERN_GAME_MEMORY_ROOT redirects default log/JSONL paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory import memory_paths


def test_default_paths_under_game_theory_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATTERN_GAME_MEMORY_ROOT", raising=False)
    assert memory_paths.memory_root() is None
    assert memory_paths.default_logs_root().name == "logs"
    assert memory_paths.default_run_memory_jsonl().name == "run_memory.jsonl"


def test_memory_root_redirects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ram"
    root.mkdir()
    monkeypatch.setenv("PATTERN_GAME_MEMORY_ROOT", str(root))
    assert memory_paths.default_logs_root() == root / "logs"
    assert memory_paths.default_run_memory_jsonl() == root / "run_memory.jsonl"
    assert memory_paths.default_experience_log_jsonl() == root / "experience_log.jsonl"
    memory_paths.ensure_memory_root_tree()
    assert (root / "logs").is_dir()
