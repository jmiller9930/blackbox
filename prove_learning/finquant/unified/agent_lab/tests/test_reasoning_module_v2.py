"""Tests for RMv2 — reasoning_module_v2.py

Validates:
  - Clean decision output contract
  - Quality-gated retrieval (obs threshold, win_rate threshold, status gate)
  - Regime detection
  - Guard rail vetoes
  - LLM fallback to rule on failure
  - Memory hybrid path
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reasoning_module_v2 import (
    RMConfig,
    RMDecision,
    ReasoningModule,
    apply_guard_rails,
)
from retrieval import retrieve_eligible


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trend_bars(n: int = 22, price: float = 100.0, atr_pct: float = 0.012) -> list[dict]:
    bars = []
    for i in range(n):
        price += 0.8 + i * 0.02
        bars.append({
            "timestamp": f"2024-01-01T{i:02d}:00:00Z",
            "open": price - 0.3,
            "high": price + 1.2,
            "low": price - 1.0,
            "close": price,
            "volume": 1200 + i * 80,
            "rsi_14": min(68.0, 52.0 + i * 0.7),
            "ema_20": price * 0.98,
            "atr_14": price * atr_pct,
        })
    return bars


def _write_record(f, *, retrieval_enabled=True, symbol="SOL-PERP",
                  entry_action="ENTER_LONG", pattern_obs=10,
                  pattern_win_rate=0.70, pattern_status="provisional",
                  record_id="lr_test001", regime="trending_up"):
    rec = {
        "schema": "finquant_learning_record_v1",
        "record_id": record_id,
        "symbol": symbol,
        "entry_action_v1": entry_action,
        "retrieval_enabled_v1": retrieval_enabled,
        "grade_v1": "PASS",
        "pattern_id_v1": f"pat_{record_id}",
        "pattern_win_rate_v1": pattern_win_rate,
        "pattern_total_obs_v1": pattern_obs,
        "pattern_status_v1": pattern_status,
        "pattern_expectancy_v1": 0.5,
        "regime_v1": regime,
    }
    f.write(json.dumps(rec) + "\n")


# ---------------------------------------------------------------------------
# RMDecision contract
# ---------------------------------------------------------------------------

def test_rm_decision_has_required_fields():
    rm = ReasoningModule(config=RMConfig(use_llm=False))
    d = rm.decide(bars=_trend_bars(), symbol="SOL-PERP", timeframe_minutes=15)
    assert isinstance(d, RMDecision)
    assert d.action in ("ENTER_LONG", "ENTER_SHORT", "NO_TRADE", "HOLD", "EXIT")
    assert 0.0 <= d.confidence <= 1.0
    assert isinstance(d.thesis, str) and len(d.thesis) > 0
    assert isinstance(d.source, str)
    assert isinstance(d.regime, str)
    assert isinstance(d.memory_used, list)


def test_rm_decision_to_dict():
    rm = ReasoningModule(config=RMConfig(use_llm=False))
    d = rm.decide(bars=_trend_bars(), symbol="SOL-PERP", timeframe_minutes=15)
    out = d.to_dict()
    assert out["schema"] == "rm_decision_v2"
    assert "action" in out
    assert "confidence" in out
    assert "source" in out
    assert "regime" in out


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------

def test_guard_blocks_entry_in_chop():
    bar = {"rsi_14": 55.0, "atr_14": 0.10, "close": 100.0}
    action, reason = apply_guard_rails("ENTER_LONG", 0.80, bar, "ranging")
    assert action == "NO_TRADE"
    assert "chop" in reason


def test_guard_blocks_entry_overbought_rsi():
    bar = {"rsi_14": 75.0, "atr_14": 1.5, "close": 100.0}
    action, reason = apply_guard_rails("ENTER_LONG", 0.80, bar, "trending_up")
    assert action == "NO_TRADE"
    assert "overbought" in reason


def test_guard_blocks_entry_low_rsi():
    bar = {"rsi_14": 42.0, "atr_14": 1.5, "close": 100.0}
    action, reason = apply_guard_rails("ENTER_LONG", 0.80, bar, "ranging")
    assert action == "NO_TRADE"
    assert "rsi_too_low" in reason


def test_guard_blocks_short_in_uptrend():
    bar = {"rsi_14": 45.0, "atr_14": 1.5, "close": 100.0}
    action, reason = apply_guard_rails("ENTER_SHORT", 0.80, bar, "trending_up")
    assert action == "NO_TRADE"
    assert "short_in_uptrend" in reason


def test_guard_passes_valid_long_entry():
    bar = {"rsi_14": 58.0, "atr_14": 1.0, "close": 100.0}  # ATR% = 1.0% > 0.60% expand
    action, reason = apply_guard_rails("ENTER_LONG", 0.75, bar, "trending_up")
    assert action == "ENTER_LONG"
    assert reason == ""


def test_guard_blocks_low_confidence():
    bar = {"rsi_14": 58.0, "atr_14": 1.0, "close": 100.0}
    action, reason = apply_guard_rails("ENTER_LONG", 0.10, bar, "trending_up")
    assert action == "NO_TRADE"
    assert "confidence" in reason and "low" in reason


# ---------------------------------------------------------------------------
# Quality-gated retrieval
# ---------------------------------------------------------------------------

def test_retrieval_blocked_insufficient_obs():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_record(f, pattern_obs=3, pattern_win_rate=0.80)  # obs < 5
        path = f.name
    try:
        case = {"symbol": "SOL-PERP", "regime_v1": "trending_up"}
        config = {
            "retrieval_enabled_default_v1": True,
            "retrieval_max_records_v1": 5,
            "retrieval_min_obs_v1": 5,
            "retrieval_min_win_rate_v1": 0.55,
        }
        records, trace = retrieve_eligible(path, case, config)
        assert records == []
        assert any("insufficient_obs" in t.get("reason", "") for t in trace)
    finally:
        os.unlink(path)


def test_retrieval_blocked_low_win_rate():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_record(f, pattern_obs=10, pattern_win_rate=0.40)  # below 0.55
        path = f.name
    try:
        case = {"symbol": "SOL-PERP"}
        config = {
            "retrieval_enabled_default_v1": True,
            "retrieval_max_records_v1": 5,
            "retrieval_min_obs_v1": 5,
            "retrieval_min_win_rate_v1": 0.55,
        }
        records, trace = retrieve_eligible(path, case, config)
        assert records == []
        assert any("low_win_rate" in t.get("reason", "") for t in trace)
    finally:
        os.unlink(path)


def test_retrieval_blocked_candidate_status():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_record(f, pattern_obs=10, pattern_win_rate=0.70, pattern_status="candidate")
        path = f.name
    try:
        case = {"symbol": "SOL-PERP"}
        config = {
            "retrieval_enabled_default_v1": True,
            "retrieval_max_records_v1": 5,
            "retrieval_min_obs_v1": 5,
            "retrieval_min_win_rate_v1": 0.55,
        }
        records, trace = retrieve_eligible(path, case, config)
        assert records == []
        assert any("disqualified_status" in t.get("reason", "") for t in trace)
    finally:
        os.unlink(path)


def test_retrieval_blocked_retired_status():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_record(f, pattern_obs=20, pattern_win_rate=0.80, pattern_status="retired")
        path = f.name
    try:
        case = {"symbol": "SOL-PERP"}
        config = {
            "retrieval_enabled_default_v1": True,
            "retrieval_max_records_v1": 5,
            "retrieval_min_obs_v1": 5,
            "retrieval_min_win_rate_v1": 0.55,
        }
        records, trace = retrieve_eligible(path, case, config)
        assert records == []
    finally:
        os.unlink(path)


def test_retrieval_passes_quality_record():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_record(f, pattern_obs=10, pattern_win_rate=0.70, pattern_status="provisional")
        path = f.name
    try:
        case = {"symbol": "SOL-PERP"}
        config = {
            "retrieval_enabled_default_v1": True,
            "retrieval_max_records_v1": 5,
            "retrieval_min_obs_v1": 5,
            "retrieval_min_win_rate_v1": 0.55,
        }
        records, trace = retrieve_eligible(path, case, config)
        assert len(records) == 1
        assert records[0]["entry_action_v1"] == "ENTER_LONG"
        assert any(t.get("reason") == "retrieved" for t in trace)
    finally:
        os.unlink(path)


def test_retrieval_regime_mismatch_filtered():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_record(f, pattern_obs=10, pattern_win_rate=0.70,
                      pattern_status="provisional", regime="trending_up")
        path = f.name
    try:
        case = {"symbol": "SOL-PERP", "regime_v1": "ranging"}
        config = {
            "retrieval_enabled_default_v1": True,
            "retrieval_max_records_v1": 5,
            "retrieval_min_obs_v1": 5,
            "retrieval_min_win_rate_v1": 0.55,
        }
        records, trace = retrieve_eligible(path, case, config)
        assert records == []
        assert any("regime_mismatch" in t.get("reason", "") for t in trace)
    finally:
        os.unlink(path)


def test_retrieval_regime_match_passes():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_record(f, pattern_obs=10, pattern_win_rate=0.70,
                      pattern_status="provisional", regime="trending_up")
        path = f.name
    try:
        case = {"symbol": "SOL-PERP", "regime_v1": "trending_up"}
        config = {
            "retrieval_enabled_default_v1": True,
            "retrieval_max_records_v1": 5,
            "retrieval_min_obs_v1": 5,
            "retrieval_min_win_rate_v1": 0.55,
        }
        records, trace = retrieve_eligible(path, case, config)
        assert len(records) == 1
    finally:
        os.unlink(path)


def test_retrieval_ranks_higher_win_rate_first():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_record(f, pattern_obs=10, pattern_win_rate=0.60,
                      pattern_status="provisional", record_id="lr_low")
        _write_record(f, pattern_obs=10, pattern_win_rate=0.90,
                      pattern_status="provisional", record_id="lr_high")
        path = f.name
    try:
        case = {"symbol": "SOL-PERP"}
        config = {
            "retrieval_enabled_default_v1": True,
            "retrieval_max_records_v1": 1,  # cap at 1 — should pick higher win_rate
            "retrieval_min_obs_v1": 5,
            "retrieval_min_win_rate_v1": 0.55,
        }
        records, _ = retrieve_eligible(path, case, config)
        assert len(records) == 1
        assert records[0]["record_id"] == "lr_high"
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

def test_regime_detected_in_decision():
    rm = ReasoningModule(config=RMConfig(use_llm=False))
    bars = _trend_bars(n=22)
    d = rm.decide(bars=bars, symbol="SOL-PERP")
    assert d.regime in ("trending_up", "trending_down", "ranging", "volatile", "unknown")


def test_chop_bars_produce_no_trade():
    rm = ReasoningModule(config=RMConfig(use_llm=False))
    bars = []
    price = 100.0
    for i in range(22):
        price += 0.02 if i % 2 == 0 else -0.02
        bars.append({
            "open": price, "high": price + 0.02, "low": price - 0.02,
            "close": price, "volume": 200 + i,
            "rsi_14": 50.0, "ema_20": 100.0,
            "atr_14": price * 0.0008,  # 0.08% — genuine chop
            "timestamp": f"2024-01-03T{i:02d}:00:00Z",
        })
    d = rm.decide(bars=bars, symbol="SOL-PERP")
    assert d.action == "NO_TRADE"


# ---------------------------------------------------------------------------
# Self-test integration
# ---------------------------------------------------------------------------

def test_self_test_passes():
    """RMv2 --self-test must complete without error."""
    from reasoning_module_v2 import run_self_test
    run_self_test()  # raises on any assertion failure
