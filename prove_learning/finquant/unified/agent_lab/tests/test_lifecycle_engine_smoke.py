"""Smoke tests for lifecycle_engine.py"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lifecycle_engine import LifecycleEngine
from schemas import VALID_ACTIONS, SCHEMA_LIFECYCLE_DECISION

CONFIG = {
    "schema": "finquant_agent_lab_config_v1",
    "agent_id": "finquant",
    "mode": "deterministic_stub_v1",
    "use_llm_v1": False,
    "retrieval_enabled_default_v1": False,
}

BASIC_CASE = {
    "schema": "finquant_lifecycle_case_v1",
    "case_id": "smoke_basic",
    "symbol": "SOL-PERP",
    "timeframe_minutes": 5,
    "decision_start_index": 0,
    "decision_end_index": 1,
    "hidden_future_start_index": 2,
    "expected_learning_focus_v1": [],
    "candles": [
        {"timestamp": "2024-01-01T00:00:00Z", "open": 100.0, "high": 101.0,
         "low": 99.0, "close": 100.5, "volume": 1000, "rsi_14": 48.0, "ema_20": 100.0, "atr_14": 1.5},
        {"timestamp": "2024-01-01T01:00:00Z", "open": 100.5, "high": 101.5,
         "low": 100.0, "close": 101.0, "volume": 1100, "rsi_14": 52.0, "ema_20": 100.2, "atr_14": 1.6},
        {"timestamp": "2024-01-01T02:00:00Z", "open": 101.0, "high": 102.0,
         "low": 100.5, "close": 101.5, "volume": 1200, "rsi_14": 55.0, "ema_20": 100.5, "atr_14": 1.7},
    ],
}


def test_engine_runs_and_emits_decisions():
    engine = LifecycleEngine(config=CONFIG)
    decisions = engine.run_case(BASIC_CASE)
    # decision_start=0, decision_end=1 → 2 decisions
    assert len(decisions) == 2


def test_decisions_have_correct_schema():
    engine = LifecycleEngine(config=CONFIG)
    decisions = engine.run_case(BASIC_CASE)
    for d in decisions:
        assert d["schema"] == SCHEMA_LIFECYCLE_DECISION
        assert d["action"] in VALID_ACTIONS
        assert d["agent_id"] == "finquant" if "agent_id" in d else True
        assert "thesis_v1" in d
        assert "invalidation_v1" in d
        assert isinstance(d["memory_used_v1"], list)
        assert d["llm_used_v1"] is False
        assert d["decision_source_v1"] == "deterministic_stub_v1"


def test_decisions_step_indices_correct():
    engine = LifecycleEngine(config=CONFIG)
    decisions = engine.run_case(BASIC_CASE)
    assert decisions[0]["step_index"] == 0
    assert decisions[1]["step_index"] == 1


def test_no_lookahead():
    """Verify visible_bars at step N never exceeds hidden_future_start_index."""
    engine = LifecycleEngine(config=CONFIG)
    decisions = engine.run_case(BASIC_CASE)
    for d in decisions:
        context = d.get("observed_context_v1", {})
        visible = context.get("candles_visible", 0)
        step = d["step_index"]
        # Must not see candles beyond hidden_future_start_index=2
        assert visible <= BASIC_CASE["hidden_future_start_index"]


def test_single_candle_returns_no_trade():
    single = dict(BASIC_CASE, decision_end_index=0)
    engine = LifecycleEngine(config=CONFIG)
    decisions = engine.run_case(single)
    assert len(decisions) == 1
    assert decisions[0]["action"] == "NO_TRADE"
