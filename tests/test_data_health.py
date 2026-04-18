"""Pattern-game SQLite health probe (no live replay)."""

from __future__ import annotations

from renaissance_v4.game_theory.data_health import get_data_health


def test_get_data_health_shape() -> None:
    h = get_data_health()
    assert "overall_ok" in h
    assert "database_path" in h
    assert "summary_line" in h
    assert "replay_min_rows" in h
    assert h["replay_min_rows"] >= 1
