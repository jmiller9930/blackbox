"""Wiring truth for pattern-game module board (DEF-001 correlation)."""

from __future__ import annotations

from renaissance_v4.game_theory.module_board import compute_pattern_game_module_board


def test_module_board_shape_and_def001_note() -> None:
    out = compute_pattern_game_module_board()
    assert out.get("ok") is True
    assert "def001_note" in out
    mods = out["modules"]
    assert len(mods) >= 12
    ids = {m["id"] for m in mods}
    assert "groundhog" in ids
    assert "run_memory" in ids
    assert "web_ui" in ids
    for m in mods:
        assert "ok" in m
        assert isinstance(m["ok"], bool)
        assert m.get("label")
        assert "detail" in m
        assert "title" in m
        assert "body" in m
        assert "role" in m


def test_groundhog_ok_matches_env_and_file() -> None:
    out = compute_pattern_game_module_board()
    mods = {m["id"]: m for m in out["modules"]}
    gh = mods["groundhog"]
    assert gh["role"] == "behavioral_memory"
    assert gh.get("signal") in ("green", "yellow", "red")
    assert "bundle" in (gh["body"] or "").lower() or "Groundhog" in (gh["title"] or "")
