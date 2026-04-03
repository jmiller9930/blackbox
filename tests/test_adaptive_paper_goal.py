"""Adaptive paper goal: 5–15% band from market stress proxy."""

from __future__ import annotations

import os
import sqlite3

import pytest

from modules.anna_training.adaptive_paper_goal import (
    GOAL_RETURN_MAX,
    GOAL_RETURN_MIN,
    compute_adaptive_paper_goal,
)


def test_adaptive_mid_band_when_no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_MARKET_DATA_DB", "/nonexistent/no_market_data.db")
    monkeypatch.delenv("ANNA_PAPER_GOAL_FIXED_FRAC", raising=False)
    monkeypatch.setenv("ANNA_PAPER_GOAL_ADAPTIVE", "1")
    out = compute_adaptive_paper_goal(bankroll_start=100.0)
    assert out["adaptive"] is True
    assert out["stress_norm"] == 0.5
    mid = GOAL_RETURN_MIN + 0.5 * (GOAL_RETURN_MAX - GOAL_RETURN_MIN)
    assert abs(float(out["goal_return_frac"]) - mid) < 1e-6
    assert abs(float(out["goal_target_equity_usd"]) - 100.0 * (1.0 + mid)) < 1e-3


def test_adaptive_off_uses_state_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_PAPER_GOAL_ADAPTIVE", "0")
    out = compute_adaptive_paper_goal(
        bankroll_start=100.0,
        paper_wallet={"goal_return_frac": 0.12},
    )
    assert out["adaptive"] is False
    assert abs(float(out["goal_return_frac"]) - 0.12) < 1e-9
    assert abs(float(out["goal_target_equity_usd"]) - 112.0) < 1e-6


def test_fixed_frac_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_PAPER_GOAL_FIXED_FRAC", "0.08")
    out = compute_adaptive_paper_goal(bankroll_start=100.0)
    assert out["adaptive"] is False
    assert abs(float(out["goal_return_frac"]) - 0.08) < 1e-9


def test_adaptive_high_range_from_synthetic_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "market_data.db"
    monkeypatch.setenv("BLACKBOX_MARKET_DATA_DB", str(db))
    monkeypatch.setenv("ANNA_PAPER_GOAL_ADAPTIVE", "1")
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE market_ticks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          symbol TEXT NOT NULL,
          inserted_at TEXT NOT NULL,
          primary_source TEXT NOT NULL,
          primary_price REAL,
          primary_observed_at TEXT,
          primary_publish_time INTEGER,
          primary_raw_json TEXT,
          comparator_source TEXT NOT NULL,
          comparator_price REAL,
          comparator_observed_at TEXT,
          comparator_raw_json TEXT,
          tertiary_source TEXT,
          tertiary_price REAL,
          tertiary_observed_at TEXT,
          tertiary_raw_json TEXT,
          gate_state TEXT NOT NULL,
          gate_reason TEXT NOT NULL
        )
        """
    )
    # Wide swing: 100 -> 110 over ticks → high range_pct
    for i, px in enumerate([100.0, 102.0, 105.0, 108.0, 110.0] * 20):
        conn.execute(
            """
            INSERT INTO market_ticks (
              symbol, inserted_at, primary_source, primary_price, primary_observed_at,
              primary_publish_time, primary_raw_json,
              comparator_source, comparator_price, comparator_observed_at, comparator_raw_json,
              tertiary_source, tertiary_price, tertiary_observed_at, tertiary_raw_json,
              gate_state, gate_reason
            ) VALUES (?, ?, 'pyth', ?, 't', NULL, NULL, 'cb', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'ok', '')
            """,
            ("SOL-USD", f"2026-01-01T00:00:{i:03d}Z", px),
        )
    conn.commit()
    conn.close()

    out = compute_adaptive_paper_goal(bankroll_start=100.0)
    assert out["adaptive"] is True
    assert float(out["goal_return_frac"]) >= GOAL_RETURN_MIN - 1e-6
    assert float(out["goal_return_frac"]) <= GOAL_RETURN_MAX + 1e-6
    assert float(out["goal_return_frac"]) > GOAL_RETURN_MIN + 0.02
