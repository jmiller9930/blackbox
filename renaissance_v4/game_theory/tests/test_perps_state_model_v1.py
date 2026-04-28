"""Deterministic RM perps state model (Directive 2)."""

from __future__ import annotations

from renaissance_v4.game_theory.reasoning_model.perps_state_model_v1 import compute_perps_state_model_v1
from renaissance_v4.game_theory.student_proctor.contracts_v1 import CONTRACT_VERSION_STUDENT_PROCTOR_V1
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import run_entry_reasoning_pipeline_v1


def test_compute_perps_state_not_available_risk() -> None:
    ic = {
        "rsi_state": "neutral",
        "ema_trend": "bullish_trend",
        "atr_volume_state": "normal_volatility",
        "volume_state": "strong_participation",
        "support_flags_v1": {"long": True, "short": False, "no_trade": False},
    }
    out = compute_perps_state_model_v1(ic)
    assert out["perps_risk_state_v1"] == "not_available_v1"
    assert out["trend_state"] == "bullish_trend"
    assert 0.0 <= float(out["confidence_01"]) <= 1.0
    assert isinstance(out["state_flags_v1"], list)


def test_pipeline_includes_perps_state_deterministic() -> None:
    bars = [
        {"open_time": 1, "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 1000.0},
        {"open_time": 2, "open": 10.5, "high": 11.5, "low": 10.0, "close": 11.2, "volume": 1100.0},
        {"open_time": 3, "open": 11.2, "high": 12.0, "low": 11.0, "close": 11.8, "volume": 1200.0},
    ]
    pkt = {
        "bars_inclusive_up_to_t": bars,
        "symbol": "SOLUSDT",
        "candle_timeframe_minutes": 5,
    }
    ere, err, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert not err
    assert ere is not None
    ps = ere.get("perps_state_model_v1")
    assert isinstance(ps, dict)
    assert ps.get("schema") == "perps_state_model_v1"
    a = ere.get("perps_state_model_v1")
    b = ere.get("perps_state_model_v1")
    assert a == b
    ere2, err2, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert ere2 is not None and ere2.get("perps_state_model_v1") == ps


def test_entry_reasoning_emits_perps_trace_stage_v1() -> None:
    from renaissance_v4.game_theory.learning_trace_events_v1 import learning_trace_memory_sink_session_v1

    bars = [
        {"open_time": 1, "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 1000.0},
        {"open_time": 2, "open": 10.5, "high": 11.5, "low": 10.0, "close": 11.2, "volume": 1100.0},
        {"open_time": 3, "open": 11.2, "high": 12.0, "low": 11.0, "close": 11.8, "volume": 1200.0},
    ]
    pkt = {"bars_inclusive_up_to_t": bars, "symbol": "SOLUSDT", "candle_timeframe_minutes": 5}
    with learning_trace_memory_sink_session_v1() as sink:
        ere, err, _, _ = run_entry_reasoning_pipeline_v1(
            student_decision_packet=pkt,
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id="job_perps_trace_v1",
            emit_traces=True,
        )
    assert not err and ere is not None
    stages = [str(e.get("stage") or "") for e in sink if isinstance(e, dict)]
    assert "perps_state_model_evaluated_v1" in stages


def test_annex_includes_perps_under_indicator_context() -> None:
    from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
        build_student_context_annex_v1_from_entry_reasoning_eval_v1,
    )

    ere = {
        "schema": "entry_reasoning_eval_v1",
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "indicator_context_eval_v1": {"rsi_state": "neutral"},
        "perps_state_model_v1": compute_perps_state_model_v1({"rsi_state": "neutral", "ema_trend": "neutral_trend"}),
        "memory_context_eval_v1": {},
        "prior_outcome_eval_v1": {},
        "risk_inputs_v1": {},
        "risk_defined_v1": True,
        "decision_synthesis_v1": {"action": "no_trade"},
        "confidence_01": 0.5,
        "confidence_band": "medium",
    }
    annex = build_student_context_annex_v1_from_entry_reasoning_eval_v1(ere)
    ic = annex.get("indicator_context") or {}
    assert "perps_state_model_v1" in ic
