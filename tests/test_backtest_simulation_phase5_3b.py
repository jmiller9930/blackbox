"""Phase 5.3b — stored-data backtest / simulation loop tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.backtest_simulation import (
    SIMULATION_VERSION,
    SimulationRunV1,
    run_stored_simulation,
    run_stored_simulation_from_read_contract,
)
from market_data.participant_scope import ParticipantScope
from market_data.read_contracts import MarketDataReadContractV1
from market_data.store import connect_market_db, ensure_market_schema, insert_tick, ticks_chronological
from _paths import repo_root


def _scope(**overrides) -> ParticipantScope:
    d = dict(
        participant_id="p1",
        participant_type="human",
        account_id="a1",
        wallet_context="w1",
        risk_tier="tier_2",
        interaction_path="cli",
    )
    d.update(overrides)
    return ParticipantScope(**d)


def _insert(
    conn,
    *,
    inserted_at: str,
    primary_price: float,
    comparator_price: float,
    symbol: str = "SOL-USD",
    gate_state: str = "ok",
) -> None:
    insert_tick(
        conn,
        symbol=symbol,
        inserted_at=inserted_at,
        primary_source="pyth_hermes",
        primary_price=primary_price,
        primary_observed_at=inserted_at,
        primary_publish_time=1,
        primary_raw={"x": 1},
        comparator_source="coinbase",
        comparator_price=comparator_price,
        comparator_observed_at=inserted_at,
        comparator_raw={"y": 2},
        gate_state=gate_state,
        gate_reason="ok",
    )


def test_ticks_chronological_order(tmp_path: Path):
    db = tmp_path / "m.db"
    root = repo_root()
    conn = connect_market_db(db)
    ensure_market_schema(conn, root)
    _insert(conn, inserted_at="2026-01-01T10:00:00+00:00", primary_price=100.0, comparator_price=100.02)
    _insert(conn, inserted_at="2026-01-01T09:00:00+00:00", primary_price=99.0, comparator_price=99.01)
    conn.close()

    conn = connect_market_db(db)
    rows = ticks_chronological(conn, "SOL-USD")
    conn.close()
    assert [r["inserted_at"] for r in rows] == [
        "2026-01-01T09:00:00+00:00",
        "2026-01-01T10:00:00+00:00",
    ]


def test_simulation_no_rows(tmp_path: Path):
    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    conn.close()
    r = run_stored_simulation(_scope(), "SOL-USD", db_path=db)
    assert r.error is not None
    assert "no_rows" in r.error
    assert r.sample_count == 0


def test_simulation_aggregates(tmp_path: Path):
    db = tmp_path / "m.db"
    root = repo_root()
    conn = connect_market_db(db)
    ensure_market_schema(conn, root)
    # Tiny spread -> neutral for tier_2 (same pattern as strategy_eval tests)
    for i in range(3):
        _insert(
            conn,
            inserted_at=f"2026-03-26T1{i}:00:00+00:00",
            primary_price=150.0,
            comparator_price=150.005,
        )
    conn.close()

    r = run_stored_simulation(_scope(), "SOL-USD", db_path=db, max_ticks=50)
    assert r.error is None
    assert r.sample_count == 3
    assert r.strategy_version == "deterministic_spread_v1"
    assert r.simulation_version == SIMULATION_VERSION
    assert r.schema_version == "simulation_run_v1"
    assert r.window_first_inserted_at is not None
    assert r.window_last_inserted_at is not None
    assert sum(r.outcome_counts.values()) == 3
    assert r.abstain_count == r.outcome_counts["abstain"]
    assert r.skip_count == 0


def test_simulation_from_read_contract(tmp_path: Path):
    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    _insert(conn, inserted_at="2026-03-26T12:00:00+00:00", primary_price=150.0, comparator_price=150.01)
    conn.close()
    c = MarketDataReadContractV1(
        participant_id="p1",
        participant_type="human",
        account_id="a1",
        wallet_context="w1",
        risk_tier="tier_2",
        interaction_path="cli",
        market_symbol="SOL-USD",
    )
    r = run_stored_simulation_from_read_contract(c, db_path=db)
    assert r.error is None
    assert r.sample_count == 1


def test_simulation_invalid_contract(tmp_path: Path):
    db = tmp_path / "m.db"
    c = MarketDataReadContractV1(
        participant_id="p1",
        participant_type="human",
        account_id="a1",
        wallet_context="w1",
        risk_tier="tier_99",
        interaction_path="cli",
        market_symbol="SOL-USD",
    )
    r = run_stored_simulation_from_read_contract(c, db_path=db)
    assert r.error is not None


def test_simulation_max_ticks(tmp_path: Path):
    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    for i in range(5):
        _insert(
            conn,
            inserted_at=f"2026-03-26T{i:02d}:00:00+00:00",
            primary_price=150.0,
            comparator_price=150.01,
        )
    conn.close()
    r = run_stored_simulation(_scope(), "SOL-USD", db_path=db, max_ticks=2)
    assert r.error is None
    assert r.sample_count == 2


def test_simulation_run_immutable(tmp_path: Path):
    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    _insert(conn, inserted_at="2026-03-26T12:00:00+00:00", primary_price=150.0, comparator_price=150.01)
    conn.close()
    r = run_stored_simulation(_scope(), "SOL-USD", db_path=db)
    with pytest.raises(Exception):
        r.sample_count = 99  # type: ignore[misc]
