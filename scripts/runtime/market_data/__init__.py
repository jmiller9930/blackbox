"""Phase 5.1 — canonical market data recorder, store, gates, signal contract."""

from __future__ import annotations

from market_data.gates import GateState, evaluate_gates
from market_data.read_contracts import (
    MarketDataReadContractV1,
    connect_market_db_readonly,
    load_latest_tick_scoped,
    validate_market_data_read_contract,
)
from market_data.recorder import record_market_snapshot, snapshot_json
from market_data.signal_contract import SignalContractV1, validate_signal_contract
from market_data.store import connect_market_db, ensure_market_schema, insert_tick, latest_tick

__all__ = [
    "GateState",
    "MarketDataReadContractV1",
    "SignalContractV1",
    "connect_market_db",
    "connect_market_db_readonly",
    "ensure_market_schema",
    "evaluate_gates",
    "insert_tick",
    "latest_tick",
    "load_latest_tick_scoped",
    "record_market_snapshot",
    "snapshot_json",
    "validate_market_data_read_contract",
    "validate_signal_contract",
]
