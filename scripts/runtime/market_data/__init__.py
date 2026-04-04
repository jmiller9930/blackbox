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
from market_data.backtest_simulation import (
    SIMULATION_VERSION,
    SimulationRunV1,
    run_stored_simulation,
    run_stored_simulation_from_read_contract,
)
from market_data.canonical_time import floor_utc_to_5m_open, last_closed_candle_open_utc
from market_data.market_event_id import make_market_event_id, parse_market_event_id
from market_data.store import (
    connect_market_db,
    ensure_market_schema,
    fetch_bar_by_market_event_id,
    insert_tick,
    latest_stored_bars,
    latest_tick,
    ticks_chronological,
    upsert_market_bar_5m,
)
from market_data.strategy_eval import (
    EVALUATION_OUTCOMES,
    STRATEGY_VERSION,
    TIER_THRESHOLDS,
    StrategyEvaluationV1,
    evaluate_strategy,
    evaluate_strategy_from_read_contract,
)
from market_data.strategy_selection import (
    SELECTION_OUTCOMES,
    SELECTION_VERSION,
    TIER_STRATEGY_PROFILES,
    StrategySelectionV1,
    select_tier_aligned_strategy,
)
from market_data.candidate_trade import (
    CANDIDATE_TRADE_VERSION,
    CandidateTradeV1,
    build_candidate_trade_v1,
    validate_candidate_trade_v1,
)

__all__ = [
    "SIMULATION_VERSION",
    "SimulationRunV1",
    "EVALUATION_OUTCOMES",
    "GateState",
    "MarketDataReadContractV1",
    "ParticipantScope",
    "ScopedMarketDataSnapshot",
    "SignalContractV1",
    "STRATEGY_VERSION",
    "SELECTION_OUTCOMES",
    "SELECTION_VERSION",
    "CANDIDATE_TRADE_VERSION",
    "CandidateTradeV1",
    "StrategyEvaluationV1",
    "StrategySelectionV1",
    "build_candidate_trade_v1",
    "TIER_THRESHOLDS",
    "TIER_STRATEGY_PROFILES",
    "VALID_PARTICIPANT_TYPES",
    "VALID_RISK_TIERS",
    "connect_market_db",
    "connect_market_db_readonly",
    "ensure_market_schema",
    "fetch_bar_by_market_event_id",
    "floor_utc_to_5m_open",
    "last_closed_candle_open_utc",
    "latest_stored_bars",
    "make_market_event_id",
    "parse_market_event_id",
    "upsert_market_bar_5m",
    "evaluate_gates",
    "evaluate_strategy",
    "evaluate_strategy_from_read_contract",
    "select_tier_aligned_strategy",
    "insert_tick",
    "latest_tick",
    "run_stored_simulation",
    "run_stored_simulation_from_read_contract",
    "ticks_chronological",
    "load_latest_tick_scoped",
    "read_latest_scoped_tick",
    "record_market_snapshot",
    "snapshot_json",
    "validate_market_data_read_contract",
    "validate_candidate_trade_v1",
    "validate_participant_scope",
    "validate_signal_contract",
]
