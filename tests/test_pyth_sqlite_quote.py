"""Pyth primary leg loads from SQLite only (no Hermes HTTP)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.feeds_pyth import load_pyth_quote_from_db  # noqa: E402
from market_data.store import (  # noqa: E402
    connect_market_db,
    ensure_market_schema,
    insert_tick,
    latest_row_primary_leg,
)
from _paths import repo_root  # noqa: E402


def test_load_pyth_from_db_roundtrip(tmp_path: Path):
    db = tmp_path / "market_data.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    insert_tick(
        conn,
        symbol="SOL-USD",
        inserted_at="2026-03-26T12:00:00+00:00",
        primary_source="pyth_hermes",
        primary_price=100.0,
        primary_observed_at="2026-03-26T12:00:00+00:00",
        primary_publish_time=1,
        primary_raw={"x": 1},
        comparator_source="coinbase",
        comparator_price=100.1,
        comparator_observed_at="2026-03-26T12:00:00+00:00",
        comparator_raw={"y": 2},
        gate_state="ok",
        gate_reason="ok",
    )
    leg = latest_row_primary_leg(conn, "SOL-USD")
    assert leg is not None
    assert leg["primary_price"] == 100.0
    q = load_pyth_quote_from_db(conn, logical_symbol="SOL-USD")
    assert q.price == 100.0
    assert "pyth_from_market_data_db" in q.notes
    conn.close()


def test_load_pyth_empty_db(tmp_path: Path):
    db = tmp_path / "empty.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    q = load_pyth_quote_from_db(conn, logical_symbol="SOL-USD")
    assert q.price is None
    assert "pyth_db_empty_no_prior_tick" in q.notes
    conn.close()
