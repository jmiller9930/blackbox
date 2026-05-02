"""Tests for learning/outcome_simulator.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.outcome_simulator import simulate_outcome


def _bull_case():
    return {
        "case_id": "bull",
        "hidden_future_start_index": 1,
        "candles": [
            {"close": 100, "high": 100.5, "low": 99.5, "atr_14": 1.5},
            {"close": 102, "high": 103, "low": 101},
            {"close": 105, "high": 106, "low": 104},
            {"close": 108, "high": 109, "low": 107},
        ],
    }


def _bear_case():
    return {
        "case_id": "bear",
        "hidden_future_start_index": 1,
        "candles": [
            {"close": 100, "high": 100.5, "low": 99.5, "atr_14": 1.5},
            {"close": 98, "high": 99, "low": 97},
            {"close": 95, "high": 96, "low": 94},
        ],
    }


def _flat_case():
    return {
        "case_id": "flat",
        "hidden_future_start_index": 1,
        "candles": [
            {"close": 100, "high": 100.2, "low": 99.8, "atr_14": 1.0},
            {"close": 100.1, "high": 100.4, "low": 99.7},
            {"close": 99.9, "high": 100.3, "low": 99.6},
        ],
    }


def test_long_in_uptrend_wins():
    out = simulate_outcome(proposed_action="ENTER_LONG", case=_bull_case())
    assert out["direction_v1"] == "long"
    assert out["pnl_v1"] > 0
    assert out["outcome_v1"] == "win"


def test_long_in_downtrend_loses():
    out = simulate_outcome(proposed_action="ENTER_LONG", case=_bear_case())
    assert out["direction_v1"] == "long"
    assert out["pnl_v1"] < 0
    assert out["outcome_v1"] == "loss"


def test_short_in_downtrend_wins():
    out = simulate_outcome(proposed_action="ENTER_SHORT", case=_bear_case())
    assert out["direction_v1"] == "short"
    assert out["pnl_v1"] > 0
    assert out["outcome_v1"] == "win"


def test_no_trade_in_flat_market_correct():
    out = simulate_outcome(proposed_action="NO_TRADE", case=_flat_case())
    assert out["direction_v1"] == "flat"
    assert out["no_trade_correct_v1"] is True


def test_no_trade_in_strong_move_missed():
    out = simulate_outcome(proposed_action="NO_TRADE", case=_bull_case())
    assert out["no_trade_correct_v1"] is False


def test_long_hits_target_or_horizon():
    out = simulate_outcome(proposed_action="ENTER_LONG", case=_bull_case())
    assert out["hit_target_v1"] or out["closed_at_horizon_v1"]


def test_no_future_candles_returns_flat():
    case = {"case_id": "x", "hidden_future_start_index": 0, "candles": []}
    out = simulate_outcome(proposed_action="ENTER_LONG", case=case)
    assert out["pnl_v1"] == 0.0
