"""Tests for learning/pattern_signature.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.pattern_signature import (
    rsi_bucket,
    atr_bucket,
    volatility_class,
    trend_class,
    build_signature,
    build_signature_from_packet,
)


def test_rsi_bucket_buckets_correctly():
    assert rsi_bucket(75) == "rsi_70plus"
    assert rsi_bucket(58) == "rsi_55_60"
    assert rsi_bucket(30) == "rsi_under35"
    assert rsi_bucket(None) == "rsi_unknown"


def test_atr_bucket_buckets_correctly():
    assert atr_bucket(2.5) == "atr_2_3"
    assert atr_bucket(0.3) == "atr_under05"
    assert atr_bucket(None) == "atr_unknown"


def test_signature_is_deterministic():
    a = build_signature(rsi=58, atr=1.8, price_above_ema=True, price_up=True,
                        volume_expand=True, position_open=False, symbol="X", timeframe_minutes=15)
    b = build_signature(rsi=58, atr=1.8, price_above_ema=True, price_up=True,
                        volume_expand=True, position_open=False, symbol="X", timeframe_minutes=15)
    assert a["pattern_id_v1"] == b["pattern_id_v1"]


def test_different_regimes_produce_different_ids():
    a = build_signature(rsi=58, atr=1.8, price_above_ema=True, price_up=True,
                        volume_expand=True, position_open=False, symbol="X", timeframe_minutes=15)
    b = build_signature(rsi=30, atr=0.5, price_above_ema=False, price_up=False,
                        volume_expand=False, position_open=False, symbol="X", timeframe_minutes=15)
    assert a["pattern_id_v1"] != b["pattern_id_v1"]


def test_signature_human_label_readable():
    sig = build_signature(rsi=58, atr=1.8, price_above_ema=True, price_up=True,
                          volume_expand=True, position_open=False, symbol="X", timeframe_minutes=15)
    assert "trend_up" in sig["human_label_v1"]
    assert "rsi_55_60" in sig["human_label_v1"]


def test_signature_from_packet():
    packet = {
        "symbol": "SOL-PERP",
        "timeframe_minutes": 15,
        "market_math_v1": {"rsi_14_v1": 58.0, "atr_14_v1": 1.8},
        "market_context_v1": {
            "price_above_ema_v1": True,
            "price_up_v1": True,
            "volume_expand_v1": True,
        },
    }
    sig = build_signature_from_packet(packet, position_open=False)
    assert "pattern_id_v1" in sig
    assert sig["components_v1"]["symbol_v1"] == "SOL-PERP"
