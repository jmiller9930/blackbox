"""GT_DIRECTIVE_031 — pattern_memory_evaluated_v1 persisted for student_test isolation."""

from __future__ import annotations

from typing import Any

import pytest

from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import (
    run_entry_reasoning_pipeline_v1,
)


def _bars_uptrend(n: int = 90) -> list[dict[str, Any]]:
    t0, step = 1_000_000, 300_000
    out: list[dict[str, Any]] = []
    for i in range(n):
        p = 100.0 + i * 0.15
        out.append(
            {
                "open_time": t0 + i * step,
                "symbol": "G031",
                "open": p,
                "high": p + 0.2,
                "low": p - 0.1,
                "close": p + 0.05,
                "volume": 1000.0 + i * 2,
            }
        )
    return out


def test_pattern_memory_emit_when_student_test_isolation_even_if_emit_traces_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closure: RM must still call learning_trace append for pattern_memory under isolation."""
    monkeypatch.setenv("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", "1")
    monkeypatch.setenv("PATTERN_GAME_LEARNING_TRACE_EVENTS", "1")

    captured: list[dict[str, Any]] = []

    def _capture(**kwargs: Any) -> Any:
        captured.append(dict(kwargs))
        from pathlib import Path

        return Path("/dev/null")

    # Instrumentation imports append at module load — patch that binding, not only learning_trace_events_v1.
    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_trace_instrumentation_v1.append_learning_trace_event_from_kwargs_v1",
        _capture,
    )

    bars = _bars_uptrend(90)
    pkt = {
        "schema": "student_decision_packet_v1",
        "symbol": "G031",
        "candle_timeframe_minutes": 5,
        "decision_open_time_ms": int(bars[-1]["open_time"]),
        "bars_inclusive_up_to_t": bars,
    }
    ere, err, _tr, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="iso_proof_job",
        emit_traces=False,
        scenario_id="scen",
        trade_id="trade_iso_01",
    )
    assert not err and ere
    pm_rows = [x for x in captured if str(x.get("stage") or "") == "pattern_memory_evaluated_v1"]
    assert len(pm_rows) == 1
    ep = pm_rows[0].get("evidence_payload") or {}
    assert isinstance(ep.get("perps_pattern_signature_v1"), dict)
    assert isinstance(ep.get("pattern_memory_eval_v1"), dict)
    assert isinstance(ep.get("top_matches_v1"), list)
    assert "pattern_effect_to_score_v1" in ep
    assert "pattern_memory_score" in (ere.get("decision_synthesis_v1") or {})
