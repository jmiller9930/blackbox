"""Tests for market_data_bridge.py — uses synthetic bars, no real DB."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from market_data_bridge import (
    rollup_bars,
    compute_indicators,
    pack_lifecycle_case,
    generate_cases_from_bars,
)


def _make_bars(n: int, base_price: float = 100.0, base_vol: float = 1000.0) -> list[dict]:
    bars = []
    for i in range(n):
        close = base_price + i * 0.1
        bars.append({
            "timestamp": f"2024-01-{(i // (24 * 12)) + 1:02d}T{((i * 5) // 60) % 24:02d}:{((i * 5) % 60):02d}:00Z",
            "open": close - 0.05,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": base_vol + i * 10,
        })
    return bars


def test_rollup_5m_to_15m():
    bars_5m = _make_bars(30)
    rolled = rollup_bars(bars_5m, 15)
    assert len(rolled) == 10
    assert rolled[0]["open"] == bars_5m[0]["open"]
    assert rolled[0]["close"] == bars_5m[2]["close"]
    assert rolled[0]["high"] == max(b["high"] for b in bars_5m[:3])


def test_rollup_no_change_if_already_target():
    bars = _make_bars(10)
    rolled = rollup_bars(bars, 5)
    assert len(rolled) == 10


def test_compute_indicators_adds_fields():
    bars = _make_bars(30)
    enriched = compute_indicators(bars)
    # RSI and EMA need enough bars to compute; ATR needs 15+
    has_rsi = any(b.get("rsi_14") is not None for b in enriched)
    has_ema = any(b.get("ema_20") is not None for b in enriched)
    has_atr = any(b.get("atr_14") is not None for b in enriched)
    assert has_rsi
    assert has_ema
    assert has_atr


def test_pack_lifecycle_case_schema():
    bars = compute_indicators(_make_bars(40))
    case = pack_lifecycle_case(
        bars,
        case_id="test_case_pack",
        symbol="SOL-PERP",
        timeframe_minutes=15,
        context_candles=20,
        decision_steps=3,
        outcome_candles=5,
    )
    assert case["schema"] == "finquant_lifecycle_case_v1"
    assert case["decision_start_index"] == 20
    assert case["decision_end_index"] == 22
    assert case["hidden_future_start_index"] == 23
    assert len(case["candles"]) == 20 + 3 + 5


def test_pack_lifecycle_case_no_lookahead():
    bars = compute_indicators(_make_bars(40))
    case = pack_lifecycle_case(
        bars,
        case_id="test_lookahead",
        symbol="SOL-PERP",
        timeframe_minutes=15,
        context_candles=20,
        decision_steps=3,
        outcome_candles=5,
    )
    # Decision steps must be within hidden boundary
    assert case["decision_end_index"] < case["hidden_future_start_index"]


def test_generate_cases_produces_multiple():
    bars = compute_indicators(_make_bars(200))
    cases = generate_cases_from_bars(
        bars,
        symbol="SOL-PERP",
        timeframe_minutes=15,
        case_prefix="gen_test",
        context_candles=20,
        decision_steps=3,
        outcome_candles=5,
        stride=3,
    )
    assert len(cases) > 1
    for case in cases:
        assert case["schema"] == "finquant_lifecycle_case_v1"
        assert case["decision_start_index"] == 20


def test_generate_cases_writes_to_disk():
    bars = compute_indicators(_make_bars(100))
    cases = generate_cases_from_bars(
        bars,
        symbol="SOL-PERP",
        timeframe_minutes=15,
        case_prefix="disk_test",
        context_candles=20,
        decision_steps=3,
        outcome_candles=5,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        for case in cases:
            p = os.path.join(tmpdir, f"{case['case_id']}.json")
            with open(p, "w") as f:
                json.dump(case, f)
            loaded = json.load(open(p))
            assert loaded["schema"] == "finquant_lifecycle_case_v1"
