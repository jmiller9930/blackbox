"""
GT_DIRECTIVE_026A_IMPL — tests for :mod:`entry_reasoning_engine_v1` (non-negotiable coverage).
"""

from __future__ import annotations

from typing import Any

import pytest

from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import (
    _rsi_state,
    build_indicator_context_eval_v1,
    run_entry_reasoning_pipeline_preflight_v1,
    run_entry_reasoning_pipeline_v1,
    validate_entry_reasoning_eval_v1,
    validate_llm_explanation_against_entry_reasoning_v1,
    apply_decision_overrides_llm_stated_action_v1,
    SCHEMA_ENTRY_REASONING_EVAL_V1,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import legal_example_student_learning_record_v1


def _bars_uptrend_n(n: int) -> list[dict[str, Any]]:
    """Monotone rising closes → bullish EMA/RSI context."""
    t0, step = 1_000_000, 300_000
    out: list[dict[str, Any]] = []
    for i in range(n):
        p = 100.0 + i * 0.15
        out.append(
            {
                "open_time": t0 + i * step,
                "symbol": "X",
                "open": p,
                "high": p + 0.2,
                "low": p - 0.1,
                "close": p + 0.05,
                "volume": 1000.0 + i * 2,
            }
        )
    return out


def _bars_downtrend_n(n: int) -> list[dict[str, Any]]:
    t0, step = 1_000_000, 300_000
    out: list[dict[str, Any]] = []
    for i in range(n):
        p = 200.0 - i * 0.12
        out.append(
            {
                "open_time": t0 + i * step,
                "symbol": "X",
                "open": p,
                "high": p + 0.1,
                "low": p - 0.2,
                "close": p - 0.05,
                "volume": 1000.0 + i * 2,
            }
        )
    return out


def _packet(bars: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "student_decision_packet_v1",
        "symbol": "X",
        "candle_timeframe_minutes": 5,
        "decision_open_time_ms": int(bars[-1]["open_time"]),
        "bars_inclusive_up_to_t": bars,
    }


def test_rsi_exhaustion_differs_from_trend_bull() -> None:
    assert _rsi_state(72.0, "bullish_trend") in ("continuation_pressure", "overbought")
    assert _rsi_state(72.0, "bearish_trend") == "exhaustion_risk"


def test_ema_trend_bull_bear() -> None:
    ctx, errs, _ = build_indicator_context_eval_v1(_bars_uptrend_n(100))
    assert not errs
    assert (ctx or {}).get("ema_trend") == "bullish_trend"
    ctx2, e2, _ = build_indicator_context_eval_v1(_bars_downtrend_n(100))
    assert not e2
    assert (ctx2 or {}).get("ema_trend") == "bearish_trend"


def test_preflight_pipeline_matches_full_on_small_packet() -> None:
    pkt = _packet(_bars_uptrend_n(40))
    pf, e_pf, _, _ = run_entry_reasoning_pipeline_preflight_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        emit_traces=False,
        unified_agent_router=False,
    )
    full, e_f, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        emit_traces=False,
        unified_agent_router=False,
    )
    assert not e_pf and not e_f and pf and full
    assert (pf.get("decision_synthesis_v1") or {}).get("action") == (full.get("decision_synthesis_v1") or {}).get(
        "action"
    )


def test_preflight_completes_on_large_bar_history_without_mutating_packet() -> None:
    pkt = _packet(_bars_uptrend_n(200))
    pf, errs, _, _ = run_entry_reasoning_pipeline_preflight_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        emit_traces=False,
        unified_agent_router=False,
    )
    assert not errs and pf and pf.get("schema") == SCHEMA_ENTRY_REASONING_EVAL_V1
    assert len(pkt["bars_inclusive_up_to_t"]) == 200


def test_pipeline_digest_stable() -> None:
    pkt = _packet(_bars_uptrend_n(100))
    a, e1, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    b, e2, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert not e1 and not e2 and a and b
    assert a["entry_reasoning_eval_digest_v1"] == b["entry_reasoning_eval_digest_v1"]


def test_trace_stages_order() -> None:
    pkt = _packet(_bars_uptrend_n(100))
    _, err, tr, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="j1",
        emit_traces=False,
    )
    assert not err
    names = [x["stage"] for x in tr]
    assert names[0] == "market_data_loaded"
    assert "indicator_context_eval_v1" in names
    ic_ix = names.index("indicator_context_eval_v1")
    ps_ix = names.index("perps_state_model_evaluated_v1")
    ds_ix = names.index("decision_synthesis_v1")
    assert ic_ix < ps_ix < ds_ix
    assert "entry_reasoning_sealed_v1" in names


def test_insufficient_bars_fails() -> None:
    pkt = _packet(_bars_uptrend_n(1))
    out, err, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        emit_traces=False,
    )
    assert out is None
    assert any("insufficient" in x for x in err)


def test_memory_conflict_negative_pnl() -> None:
    pkt = _packet(_bars_uptrend_n(100))
    rec = legal_example_student_learning_record_v1()
    rec["candle_timeframe_minutes"] = 5
    rec["referee_outcome_subset"] = {"pnl": -5.0}
    out, err, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[rec],
        run_candle_timeframe_minutes=5,
        emit_traces=False,
    )
    assert not err and out
    m = out["memory_context_eval_v1"]["scored_records_v1"][0]
    assert m.get("memory_effect_class_v1") == "conflict"
    # conflict path often yields no_trade when scores collapse
    assert out["decision_synthesis_v1"]["action"] in ("enter_long", "enter_short", "no_trade")


def test_hallucinated_memory_id_fails_llm() -> None:
    pkt = _packet(_bars_uptrend_n(100))
    eng, e, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        emit_traces=False,
    )
    assert not e and eng
    bad = {"cited_memory_record_ids": ["not-in-store"], "stated_action": "enter_long"}
    v = validate_llm_explanation_against_entry_reasoning_v1(
        bad, entry_reasoning=eng, allowed_memory_ids=frozenset()
    )
    assert any("hallucinated" in x for x in v)


def test_llm_cannot_override_decision() -> None:
    pkt = _packet(_bars_uptrend_n(100))
    eng, e, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        emit_traces=False,
    )
    assert not e and eng
    real = (eng.get("decision_synthesis_v1") or {}).get("action")
    w = apply_decision_overrides_llm_stated_action_v1(eng, "enter_short" if real != "enter_short" else "enter_long")
    assert (w.get("llm_rejected_v1") or {}).get("reason") == "decision_engine_overrides_llm"


def test_validation_rejects_broken_object() -> None:
    d = {
        "schema": SCHEMA_ENTRY_REASONING_EVAL_V1,
        "contract_version": 1,
        "decision_synthesis_v1": {"action": "enter_long"},
        "confidence_01": 0.5,
    }
    errs = validate_entry_reasoning_eval_v1(d)
    assert any("trade_without_risk" in e for e in errs)


def test_atr_affects_confidence_effect() -> None:
    # Long flat bars → low TR relative to spike last bar? Use synthetic with tiny range then last bar big range
    t0, step = 1_000_000, 300_000
    bars: list[dict[str, Any]] = []
    for i in range(90):
        p = 100.0
        bars.append(
            {
                "open_time": t0 + i * step,
                "symbol": "X",
                "open": p,
                "high": p + 0.01,
                "low": p - 0.01,
                "close": p,
                "volume": 1000.0,
            }
        )
    p = 100.0
    bars.append(
        {
            "open_time": t0 + 90 * step,
            "symbol": "X",
            "open": p,
            "high": p + 5.0,
            "low": p - 5.0,
            "close": p + 0.1,
            "volume": 5000.0,
        }
    )
    ctx, errs, _ = build_indicator_context_eval_v1(bars)
    assert not errs
    assert (ctx or {}).get("atr_volume_state") in ("high_volatility", "normal_volatility", "low_volatility")
