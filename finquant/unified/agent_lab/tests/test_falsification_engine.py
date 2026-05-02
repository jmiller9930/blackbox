"""Tests for learning/falsification_engine.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.falsification_engine import falsify


def _case(*, hide_from: int, candles: list[dict]) -> dict:
    return {
        "case_id": "test_case",
        "hidden_future_start_index": hide_from,
        "candles": candles,
    }


def test_no_trade_confirmed_when_abstained_and_pass():
    case = _case(hide_from=2, candles=[
        {"close": 100}, {"close": 100.5}, {"close": 100.3}
    ])
    eval_ = {"final_status_v1": "PASS", "entry_quality_v1": "correctly_abstained",
             "no_trade_correctness_v1": "correctly_stood_down"}
    v = falsify(proposed_action="NO_TRADE", case=case, evaluation=eval_,
                actions_taken=["NO_TRADE", "NO_TRADE"])
    assert v["verdict_v1"] == "confirmed"


def test_long_confirmed_when_pass_and_price_up():
    case = _case(hide_from=1, candles=[
        {"close": 100}, {"close": 102}, {"close": 103}
    ])
    eval_ = {"final_status_v1": "PASS", "entry_quality_v1": "entered_as_expected"}
    v = falsify(proposed_action="ENTER_LONG", case=case, evaluation=eval_,
                actions_taken=["ENTER_LONG", "HOLD"])
    assert v["verdict_v1"] == "confirmed"
    assert v["expectation_met_v1"] is True


def test_long_rejected_when_fail():
    case = _case(hide_from=1, candles=[
        {"close": 100}, {"close": 99}, {"close": 98}
    ])
    eval_ = {"final_status_v1": "FAIL"}
    v = falsify(proposed_action="ENTER_LONG", case=case, evaluation=eval_,
                actions_taken=["ENTER_LONG", "HOLD"])
    assert v["verdict_v1"] == "rejected"
    assert v["invalidation_triggered_v1"] is True


def test_long_inconclusive_when_no_entry_taken():
    case = _case(hide_from=1, candles=[
        {"close": 100}, {"close": 102}, {"close": 103}
    ])
    eval_ = {"final_status_v1": "INFO"}
    v = falsify(proposed_action="ENTER_LONG", case=case, evaluation=eval_,
                actions_taken=["NO_TRADE", "NO_TRADE"])
    assert v["verdict_v1"] == "inconclusive"


def test_actual_outcome_includes_price_change():
    case = _case(hide_from=1, candles=[
        {"close": 100}, {"close": 105}
    ])
    eval_ = {"final_status_v1": "PASS"}
    v = falsify(proposed_action="ENTER_LONG", case=case, evaluation=eval_,
                actions_taken=["ENTER_LONG"])
    assert v["actual_outcome_v1"]["entry_close_v1"] == 100
    assert v["actual_outcome_v1"]["last_outcome_close_v1"] == 105
    assert v["actual_outcome_v1"]["price_change_v1"] == 5
