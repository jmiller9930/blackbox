"""Phase 5 — canonical market data: recorder, store, gates, signal contract, scoped reads, strategy eval."""

from __future__ import annotations

from market_data.gates import GateState, evaluate_gates
from market_data.participant_scope import (
    VALID_PARTICIPANT_TYPES,
    VALID_RISK_TIERS,
    ParticipantScope,
    validate_participant_scope,
)
from market_data.read_contracts import (
    MarketDataReadContractV1,
    connect_market_db_readonly,
    load_latest_tick_scoped,
    validate_market_data_read_contract,
)
from market_data.recorder import record_market_snapshot, snapshot_json
from market_data.scoped_reader import ScopedMarketDataSnapshot, read_latest_scoped_tick
from market_data.signal_contract import SignalContractV1, validate_signal_contract
from market_data.store import connect_market_db, ensure_market_schema, insert_tick, latest_tick
from market_data.strategy_eval import (
    EVALUATION_OUTCOMES,
    STRATEGY_VERSION,
    TIER_THRESHOLDS,
    StrategyEvaluationV1,
    evaluate_strategy,
    evaluate_strategy_from_read_contract,
)

__all__ = [
    "EVALUATION_OUTCOMES",
    "GateState",
    "MarketDataReadContractV1",
    "ParticipantScope",
    "ScopedMarketDataSnapshot",
    "SignalContractV1",
    "STRATEGY_VERSION",
    "StrategyEvaluationV1",
    "TIER_THRESHOLDS",
    "VALID_PARTICIPANT_TYPES",
    "VALID_RISK_TIERS",
    "connect_market_db",
    "connect_market_db_readonly",
    "ensure_market_schema",
    "evaluate_gates",
    "evaluate_strategy",
    "evaluate_strategy_from_read_contract",
    "insert_tick",
    "latest_tick",
    "load_latest_tick_scoped",
    "read_latest_scoped_tick",
    "record_market_snapshot",
    "snapshot_json",
    "validate_market_data_read_contract",
    "validate_participant_scope",
    "validate_signal_contract",
]
