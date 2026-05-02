"""Tests for data_contracts.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_contracts import build_input_packet


def test_build_input_packet_has_memory_and_hypotheses():
    case = {
        "case_id": "pkt_001",
        "symbol": "SOL-PERP",
        "timeframe_minutes": 60,
    }
    visible = [
        {"close": 100.0, "volume": 1000, "rsi_14": 50.0, "ema_20": 99.8, "atr_14": 1.2},
        {"close": 101.0, "volume": 1200, "rsi_14": 56.0, "ema_20": 100.1, "atr_14": 1.6},
    ]
    prior = [{
        "record_id": "lr_001",
        "retrieval_enabled_v1": True,
        "entry_action_v1": "ENTER_LONG",
        "grade_v1": "PASS",
    }]
    pkt = build_input_packet(
        case=case,
        step_index=1,
        visible_bars=visible,
        config={"runtime_data_window_months_v1": 12, "runtime_interval_v1": "1h"},
        prior_records=prior,
    )
    assert pkt["schema"] == "finquant_input_packet_v1"
    assert pkt["memory_context_v1"]["matched_record_count_v1"] == 1
    assert pkt["memory_context_v1"]["long_bias_count_v1"] == 1
    assert len(pkt["strategy_hypotheses_v1"]) == 5
    assert pkt["market_context_v1"]["price_up_v1"] is True
