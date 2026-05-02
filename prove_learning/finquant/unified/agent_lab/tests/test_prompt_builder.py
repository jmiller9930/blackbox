"""Tests for prompt_builder.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompt_builder import build_prompt, SYSTEM_PROMPT


SAMPLE_PACKET = {
    "schema": "finquant_input_packet_v1",
    "case_id": "test_prompt_001",
    "step_index": 1,
    "symbol": "SOL-PERP",
    "timeframe_minutes": 15,
    "runtime_data_window_months_v1": 18,
    "runtime_interval_v1": "15m",
    "candles_visible_v1": 22,
    "market_math_v1": {
        "close_v1": 101.5,
        "prev_close_v1": 100.8,
        "price_delta_v1": 0.7,
        "pct_change_v1": 0.00695,
        "ema_gap_v1": 1.1,
        "atr_14_v1": 1.8,
        "rsi_14_v1": 57.3,
        "volume_delta_v1": 200.0,
    },
    "market_context_v1": {
        "price_above_ema_v1": True,
        "price_up_v1": True,
        "volume_expand_v1": True,
        "atr_expanded_v1": True,
        "rsi_state_v1": "bullish_range",
        "volatility_state_v1": "expanded",
    },
    "memory_context_v1": {
        "matched_record_count_v1": 1,
        "matched_record_ids_v1": ["lr_abc123"],
        "long_bias_count_v1": 1,
        "short_bias_count_v1": 0,
        "no_trade_bias_count_v1": 0,
        "best_grade_v1": "PASS",
        "memory_influence_available_v1": True,
    },
    "strategy_hypotheses_v1": [
        {"strategy_family_v1": "trend_continuation", "action_v1": "ENTER_LONG", "score_v1": 0.85},
        {"strategy_family_v1": "no_trade_guard", "action_v1": "NO_TRADE", "score_v1": 0.2},
    ],
}


def test_prompt_contains_symbol():
    prompt = build_prompt(SAMPLE_PACKET)
    assert "SOL-PERP" in prompt


def test_prompt_contains_rsi_and_atr():
    prompt = build_prompt(SAMPLE_PACKET)
    assert "57.3" in prompt or "RSI" in prompt
    assert "1.8" in prompt or "ATR" in prompt


def test_prompt_contains_memory_context():
    prompt = build_prompt(SAMPLE_PACKET)
    assert "MEMORY" in prompt.upper()
    assert "long" in prompt.lower() or "Long" in prompt


def test_prompt_flat_position_says_flat():
    prompt = build_prompt(SAMPLE_PACKET, position_open=False)
    assert "FLAT" in prompt
    assert "NO_TRADE" in prompt or "ENTER_LONG" in prompt or "ENTER_SHORT" in prompt


def test_prompt_open_position_says_hold_or_exit():
    prompt = build_prompt(SAMPLE_PACKET, position_open=True, entry_price=99.5)
    assert "OPEN" in prompt
    assert "HOLD" in prompt or "EXIT" in prompt


def test_prompt_no_memory_says_no_eligible():
    no_mem_packet = dict(SAMPLE_PACKET)
    no_mem_packet["memory_context_v1"] = {
        "matched_record_count_v1": 0,
        "memory_influence_available_v1": False,
    }
    prompt = build_prompt(no_mem_packet)
    assert "No validated patterns" in prompt or "No eligible" in prompt


def test_system_prompt_mentions_finquant():
    assert "FinQuant" in SYSTEM_PROMPT


def test_system_prompt_mentions_json():
    assert "JSON" in SYSTEM_PROMPT


def test_prompt_contains_hypotheses():
    prompt = build_prompt(SAMPLE_PACKET)
    assert "trend_continuation" in prompt
    assert "0.85" in prompt
