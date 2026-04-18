"""Anna visible window: narrow OHLCV slice + contract."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from renaissance_v4.game_theory.anna_visible_window import (
    fetch_last_bars_for_window,
    format_visible_window_for_prompt,
)


def test_fetch_last_bars_empty_db(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite3"
    rows, err = fetch_last_bars_for_window(
        db_path=missing, symbol="SOLUSDT", table="market_bars_5m", window_minutes=5.0
    )
    assert rows == []
    assert err is not None


def test_fetch_last_bars_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "t.sqlite3"
    with sqlite3.connect(p) as conn:
        conn.execute(
            """
            CREATE TABLE market_bars_5m (
                symbol TEXT, open_time INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL
            )
            """
        )
        for i in range(3):
            conn.execute(
                "INSERT INTO market_bars_5m VALUES (?,?,?,?,?,?,?)",
                ("SOLUSDT", 1000 + i * 300_000, 1.0, 1.1, 0.9, 1.05, 100.0 + i),
            )
        conn.commit()
    rows, err = fetch_last_bars_for_window(
        db_path=p, symbol="SOLUSDT", table="market_bars_5m", window_minutes=5.0
    )
    assert err is None
    assert len(rows) == 1  # one 5m bar covers 5 minutes
    assert rows[0]["close"] == pytest.approx(1.05)


def test_format_visible_includes_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_VISIBLE_WINDOW_MINUTES", "5")
    s = format_visible_window_for_prompt(db_path=tmp_path / "missing.sqlite3", max_chars=4000)
    assert "Visibility contract" in s or "visibility" in s.lower()
    assert "full historical tape" in s.lower() or "database file missing" in s
