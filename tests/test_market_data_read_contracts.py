"""Phase 5.2a — participant-scoped market-data read contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.read_contracts import (  # noqa: E402
    MarketDataReadContractV1,
    load_latest_tick_scoped,
    validate_market_data_read_contract,
)
from market_data.store import connect_market_db, ensure_market_schema, insert_tick  # noqa: E402
from _paths import repo_root  # noqa: E402


def _contract(**overrides):
    base = dict(
        participant_id="p1",
        participant_type="human",
        account_id="a1",
        wallet_context="w1",
        risk_tier="tier_2",
        interaction_path="terminal",
        market_symbol="SOL-USD",
    )
    base.update(overrides)
    return MarketDataReadContractV1(**base)


def test_validate_missing_fields():
    c = _contract(participant_id="")
    with pytest.raises(ValueError, match="market_data_read_contract_missing_fields"):
        validate_market_data_read_contract(c)


def test_validate_bad_risk_tier():
    c = _contract(risk_tier="tier_9")
    with pytest.raises(ValueError, match="invalid_risk_tier"):
        validate_market_data_read_contract(c)


def test_load_latest_tick_scoped_roundtrip(tmp_path: Path):
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
    conn.close()

    tick, err = load_latest_tick_scoped(_contract(), db_path=db)
    assert err is None
    assert tick is not None
    assert tick["symbol"] == "SOL-USD"
    assert tick["gate_state"] == "ok"
    assert tick["participant_scope"]["participant_id"] == "p1"
    assert tick["participant_scope"]["risk_tier"] == "tier_2"


def test_load_latest_tick_scoped_missing_db(tmp_path: Path):
    missing = tmp_path / "nope.db"
    tick, err = load_latest_tick_scoped(_contract(), db_path=missing)
    assert tick is None
    assert err is not None
    assert "market_data_db_missing" in err

