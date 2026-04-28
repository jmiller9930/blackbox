"""student_reasoning_model_trace_proof_v1 — strict per-trade trace completeness."""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.game_theory.learning_trace_events_v1 import append_learning_trace_event_v1, build_learning_trace_event_v1
from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
    DECISION_SOURCE_REASONING_MODEL_V1,
)
from renaissance_v4.game_theory.tools.student_reasoning_model_trace_proof_v1 import (
    validate_student_reasoning_model_trace_for_job_v1,
)


def _append(path: Path, **kwargs) -> None:
    ev = build_learning_trace_event_v1(**kwargs)
    append_learning_trace_event_v1(ev, path=path)


def test_trace_proof_ok_synthetic_two_trades(tmp_path: Path) -> None:
    p = tmp_path / "lt.jsonl"
    jid = "proof_job_two_trades_01"
    for tid, sid in (("t1", "s1"), ("t2", "s1")):
        base = dict(
            job_id=jid,
            fingerprint="f" * 40,
            scenario_id=sid,
            trade_id=tid,
            status="pass",
            producer="test",
        )
        _append(
            path=p,
            stage="candle_timeframe_nexus_v1",
            summary="nexus",
            evidence_payload={"candle_timeframe_nexus": "student_packet", "candle_timeframe_minutes": 5},
            **base,
        )
        _append(
            path=p,
            stage="memory_retrieval_completed",
            summary="mem",
            evidence_payload={
                "student_retrieval_matches": 0,
                "retrieved_lifecycle_learning_026c_slice_count_v1": 0,
            },
            **base,
        )
        for st in (
            "market_data_loaded",
            "indicator_context_eval_v1",
            "perps_state_model_evaluated_v1",
            "memory_context_evaluated",
            "prior_outcomes_evaluated",
            "risk_reward_evaluated",
            "decision_synthesis_v1",
            "entry_reasoning_validated",
            "entry_reasoning_sealed_v1",
        ):
            _append(path=p, stage=st, summary=st, evidence_payload={}, **base)
        _append(
            path=p,
            stage="reasoning_router_decision_v1",
            summary="router",
            evidence_payload={"reasoning_router_decision_v1": {"final_route_v1": "local_only"}},
            **base,
        )
        _append(
            path=p,
            stage="reasoning_cost_governor_v1",
            summary="cost",
            evidence_payload={"reasoning_cost_governor_v1": {"ok_v1": True}},
            **base,
        )
        auth_pl = {
            "authority_mode_v1": "shadow",
            "authority_applied_v1": False,
            "authority_would_apply_v1": False,
            "referee_safety_check_v1": {"passed_v1": True},
            "decision_source_v1": DECISION_SOURCE_REASONING_MODEL_V1,
            "before_decision_snapshot_v1": {"decision_action_v1": "no_trade"},
            "after_decision_snapshot_v1": {"decision_action_v1": "no_trade"},
            "authority_reason_codes_v1": ["no_026c_retrieval_slices_v1"],
        }
        _append(
            path=p,
            stage="student_decision_authority_v1",
            summary="auth",
            evidence_payload={"student_decision_authority_v1": auth_pl},
            **base,
        )
        _append(
            path=p,
            stage="student_output_sealed",
            summary="sealed",
            evidence_payload={
                "via": "shadow_stub",
                "decision_source_v1": DECISION_SOURCE_REASONING_MODEL_V1,
            },
            **base,
        )
    rep = validate_student_reasoning_model_trace_for_job_v1(jid, path=p)
    assert rep["ok_v1"] is True
    assert rep["sealed_trade_count_v1"] == 2
    assert rep["counts_match_v1"] is True


def test_trace_proof_fails_when_authority_count_mismatch(tmp_path: Path) -> None:
    p = tmp_path / "lt2.jsonl"
    jid = "proof_job_mismatch"
    tid, sid = "t1", "s1"
    base = dict(
        job_id=jid,
        fingerprint="f" * 40,
        scenario_id=sid,
        trade_id=tid,
        status="pass",
        producer="test",
    )
    _append(
        path=p,
        stage="candle_timeframe_nexus_v1",
        summary="nexus",
        evidence_payload={"candle_timeframe_nexus": "student_packet", "candle_timeframe_minutes": 5},
        **base,
    )
    _append(
        path=p,
        stage="memory_retrieval_completed",
        summary="mem",
        evidence_payload={"student_retrieval_matches": 0, "retrieved_lifecycle_learning_026c_slice_count_v1": 0},
        **base,
    )
    for st in (
        "market_data_loaded",
        "indicator_context_eval_v1",
        "perps_state_model_evaluated_v1",
        "memory_context_evaluated",
        "prior_outcomes_evaluated",
        "risk_reward_evaluated",
        "decision_synthesis_v1",
        "entry_reasoning_validated",
        "entry_reasoning_sealed_v1",
    ):
        _append(path=p, stage=st, summary=st, evidence_payload={}, **base)
    _append(
        path=p,
        stage="reasoning_router_decision_v1",
        summary="router",
        evidence_payload={"reasoning_router_decision_v1": {"final_route_v1": "local_only"}},
        **base,
    )
    _append(
        path=p,
        stage="student_output_sealed",
        summary="sealed",
        evidence_payload={"via": "x", "decision_source_v1": DECISION_SOURCE_REASONING_MODEL_V1},
        **base,
    )
    rep = validate_student_reasoning_model_trace_for_job_v1(jid, path=p)
    assert rep["ok_v1"] is False
    assert any("authority_event_count_mismatch" in x for x in rep["errors_v1"])
