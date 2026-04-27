"""RM preflight wiring — validation, memory sink, router trace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.learning_trace_events_v1 import (
    build_learning_trace_event_v1,
    learning_trace_memory_sink_session_v1,
)
from renaissance_v4.game_theory.rm_preflight_wiring_v1 import (
    FAILED_PREFLIGHT_STATUS_V1,
    PREFLIGHT_DECISION_SNAPSHOT_TRADE_ID_V1,
    REQUIRED_RM_PREFLIGHT_STAGES_V1,
    _rm_preflight_run_decision_snapshot_isolated_v1,
    _rm_preflight_root_cause_phase_v1,
    _shrink_scenario_for_rm_preflight_v1,
    rm_preflight_enabled_v1,
    run_rm_preflight_wiring_v1,
    should_skip_rm_preflight_v1,
    validate_rm_preflight_memory_sink_v1,
)
from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
    DECISION_SOURCE_REASONING_MODEL_V1,
)


def _rm_preflight_test_subprocess_hang_entry_v1(_result_q: Any, _payload: dict[str, Any]) -> None:
    """Top-level for spawn pickling — simulates a blocked preflight child."""
    import time as _time

    _time.sleep(3.0)


@pytest.fixture(autouse=True)
def _disable_rm_preflight_subprocess_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """In-process snapshot so ``@patch(... run_rm_preflight_decision_snapshot_v1)`` applies."""
    monkeypatch.setenv("PATTERN_GAME_RM_PREFLIGHT_SUBPROCESS_ISOLATION", "0")


def test_run_decision_snapshot_isolated_hard_timeout_terminates_blocked_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from renaissance_v4.game_theory import rm_preflight_wiring_v1 as rmw

    monkeypatch.setattr(
        rmw,
        "_rm_preflight_decision_snapshot_subprocess_entry_v1",
        _rm_preflight_test_subprocess_hang_entry_v1,
    )
    r = _rm_preflight_run_decision_snapshot_isolated_v1(
        scenario={"manifest_path": "missing.json", "scenario_id": "x"},
        job_id="j_hard_timeout",
        exam_run_contract_request_v1={"student_brain_profile_v1": "memory_context_student"},
        operator_batch_audit={},
        cancel_check=None,
        hard_timeout_s=0.35,
    )
    assert r.get("mode") == "hard_timeout"


def test_validate_rm_preflight_memory_sink_ok():
    sid, tid = "scen_a", "t1"
    rows = [
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="entry_reasoning_sealed_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
        ),
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="reasoning_router_decision_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
            evidence_payload={"reasoning_router_decision_v1": {"x": 1}},
        ),
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="reasoning_cost_governor_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
        ),
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="student_decision_authority_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
            evidence_payload={
                "student_decision_authority_v1": {
                    "referee_safety_check_v1": {"passed_v1": True},
                    "decision_source_v1": DECISION_SOURCE_REASONING_MODEL_V1,
                }
            },
        ),
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="student_output_sealed",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
            evidence_payload={
                "decision_source_v1": DECISION_SOURCE_REASONING_MODEL_V1,
                "student_decision_protocol_ok_v1": True,
                "student_decision_protocol_errors_v1": [],
                "student_decision_protocol_keys_expected_v1": [],
            },
        ),
    ]
    ok, miss = validate_rm_preflight_memory_sink_v1(
        rows, scenario_id=sid, trade_id=tid, job_id="j1"
    )
    assert ok and miss == []


def test_validate_rm_preflight_memory_sink_fails_when_sealed_protocol_not_ok():
    sid, tid = "scen_a", "t1"
    rows = [
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="entry_reasoning_sealed_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
        ),
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="reasoning_router_decision_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
            evidence_payload={"reasoning_router_decision_v1": {"x": 1}},
        ),
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="reasoning_cost_governor_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
        ),
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="student_decision_authority_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
            evidence_payload={
                "student_decision_authority_v1": {
                    "referee_safety_check_v1": {"passed_v1": True},
                    "decision_source_v1": DECISION_SOURCE_REASONING_MODEL_V1,
                }
            },
        ),
        build_learning_trace_event_v1(
            job_id="j1",
            fingerprint=None,
            stage="student_output_sealed",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
            evidence_payload={
                "decision_source_v1": DECISION_SOURCE_REASONING_MODEL_V1,
                "student_decision_protocol_ok_v1": False,
                "student_decision_protocol_errors_v1": ["directional_thesis_required_for_llm_profile: missing x"],
            },
        ),
    ]
    ok, miss = validate_rm_preflight_memory_sink_v1(
        rows, scenario_id=sid, trade_id=tid, job_id="j1"
    )
    assert not ok
    assert "student_output_sealed.student_decision_protocol_incomplete_v1" in miss


def test_validate_rm_preflight_memory_sink_job_id_mismatch_fails():
    sid, tid = "scen_a", "t1"
    rows = [
        build_learning_trace_event_v1(
            job_id="wrong",
            fingerprint=None,
            stage="entry_reasoning_sealed_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
        ),
    ]
    ok, miss = validate_rm_preflight_memory_sink_v1(
        rows, scenario_id=sid, trade_id=tid, job_id="batch_job"
    )
    assert not ok
    assert any(m.startswith("job_id_not_bound_v1:") for m in miss)


def test_validate_rm_preflight_memory_sink_missing_router():
    sid, tid = "s", "t"
    rows = [
        build_learning_trace_event_v1(
            job_id="j",
            fingerprint=None,
            stage="entry_reasoning_sealed_v1",
            status="pass",
            summary="s",
            producer="p",
            scenario_id=sid,
            trade_id=tid,
        ),
    ]
    ok, miss = validate_rm_preflight_memory_sink_v1(
        rows, scenario_id=sid, trade_id=tid, job_id="j"
    )
    assert not ok
    assert "reasoning_router_decision_v1" in miss
    assert "reasoning_cost_governor_v1" in miss


def test_memory_sink_no_file_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trace_path = tmp_path / "learning_trace_events_v1.jsonl"
    trace_path.write_text("", encoding="utf-8")

    def _always_this_path() -> Path:
        return trace_path

    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_trace_events_v1.default_learning_trace_events_jsonl",
        _always_this_path,
    )
    with learning_trace_memory_sink_session_v1() as sink:
        from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import emit_reasoning_router_decision_v1

        emit_reasoning_router_decision_v1(
            job_id="job_rm_sink_test",
            fingerprint="fp",
            decision={"schema": "reasoning_router_decision_v1", "contract_version": 1},
            call_record={"api_call_attempted_v1": False},
            scenario_id="sx",
            trade_id="tx",
        )
        assert len(sink) == 1
    assert trace_path.read_text(encoding="utf-8") == ""


def test_rm_preflight_enabled_default():
    assert rm_preflight_enabled_v1() is True


def test_rm_preflight_shrink_clamps_calendar_and_sets_tail_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATTERN_GAME_RM_PREFLIGHT_MAX_CALENDAR_MONTHS", "1")
    monkeypatch.setenv("PATTERN_GAME_RM_PREFLIGHT_REPLAY_TAIL_BARS", "4444")
    s = _shrink_scenario_for_rm_preflight_v1(
        {
            "manifest_path": "m.json",
            "scenario_id": "s1",
            "evaluation_window": {"calendar_months": 24},
        }
    )
    assert s["evaluation_window"]["calendar_months"] == 1
    assert s["rm_preflight_replay_tail_bars_v1"] == 4444
    assert s["evaluation_window"].get("rm_preflight_window_clamp_v1") is True


def test_student_mandate_should_skip_returns_fatal_when_rm_preflight_env_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATTERN_GAME_RM_PREFLIGHT", "0")
    assert (
        should_skip_rm_preflight_v1(
            exam_run_contract_request_v1={"student_brain_profile_v1": "memory_context_student"}
        )
        == "rm_preflight_disabled_student_rm_contract_v1"
    )


def test_run_rm_preflight_respects_cancel_check_before_worker() -> None:
    calls = {"n": 0}

    def _cancel() -> bool:
        calls["n"] += 1
        return calls["n"] >= 1

    rep = run_rm_preflight_wiring_v1(
        scenarios=[{"manifest_path": "m.json", "scenario_id": "x"}],
        job_id="jid_cancel",
        exam_run_contract_request_v1={"student_brain_profile_v1": "memory_context_student"},
        operator_batch_audit={},
        cancel_check=_cancel,
    )
    assert rep.get("cancelled_during_preflight_v1") is True
    assert rep.get("ok_v1") is False


def test_student_mandate_run_rm_preflight_fails_when_rm_preflight_env_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATTERN_GAME_RM_PREFLIGHT", "0")
    rep = run_rm_preflight_wiring_v1(
        scenarios=[{"manifest_path": "m.json", "scenario_id": "x"}],
        job_id="jid_env_off",
        exam_run_contract_request_v1={"student_brain_profile_v1": "memory_context_student"},
        operator_batch_audit={},
    )
    assert rep["ok_v1"] is False
    assert rep["skipped_v1"] is False
    assert rep["status_v1"] == FAILED_PREFLIGHT_STATUS_V1
    assert rep.get("skip_reason_v1") == "rm_preflight_disabled_student_rm_contract_v1"


def test_required_stages_include_router():
    assert "reasoning_router_decision_v1" in REQUIRED_RM_PREFLIGHT_STAGES_V1
    assert "reasoning_cost_governor_v1" in REQUIRED_RM_PREFLIGHT_STAGES_V1


def test_rm_preflight_root_cause_timeout_prefers_timeout_hit_phase():
    rows = [
        {
            "phase": "snapshot_build_v1",
            "entered_v1": True,
            "ended_at_ms_v1": 1,
            "timeout_hit_v1": False,
        },
        {
            "phase": "rm_entry_reasoning_v1",
            "entered_v1": True,
            "ended_at_ms_v1": 2,
            "timeout_hit_v1": True,
        },
    ]
    assert (
        _rm_preflight_root_cause_phase_v1(
            rows, missing_stages_v1=["preflight_timeout_decision_snapshot_v1"]
        )
        == "rm_entry_reasoning_v1"
    )


def test_rm_preflight_root_cause_timeout_inter_phase_suffix():
    rows = [
        {
            "phase": "snapshot_build_v1",
            "entered_v1": True,
            "ended_at_ms_v1": 1,
            "timeout_hit_v1": False,
        },
        {
            "phase": "preflight_budget_exhausted_before_snapshot_v1",
            "entered_v1": False,
            "ended_at_ms_v1": None,
            "timeout_hit_v1": False,
        },
    ]
    root = _rm_preflight_root_cause_phase_v1(
        rows, missing_stages_v1=["preflight_timeout_decision_snapshot_v1"]
    )
    assert root == "preflight_timeout_inter_phase_v1:after_preflight_budget_exhausted_before_snapshot_v1"


def test_json_roundtrip_sink_event():
    ev = build_learning_trace_event_v1(
        job_id="j",
        fingerprint=None,
        stage="reasoning_cost_governor_v1",
        status="pass",
        summary="s",
        producer="p",
        scenario_id="a",
        trade_id="b",
    )
    s = json.dumps(ev)
    assert "reasoning_cost_governor_v1" in s


@patch("renaissance_v4.game_theory.rm_preflight_wiring_v1.run_rm_preflight_decision_snapshot_v1")
def test_run_rm_preflight_decision_snapshot_timeout_surfaces_v1(mock_snap) -> None:
    mock_snap.return_value = {
        "ok_v1": False,
        "scenario_id": "x",
        "trade_id": PREFLIGHT_DECISION_SNAPSHOT_TRADE_ID_V1,
        "seam_audit": None,
        "missing_stages_v1": ["preflight_timeout_decision_snapshot_v1"],
        "human_message_v1": "preflight_timeout_decision_snapshot_v1",
    }
    rep = run_rm_preflight_wiring_v1(
        scenarios=[{"manifest_path": "m.json", "scenario_id": "x"}],
        job_id="jid_timeout",
        exam_run_contract_request_v1={"student_brain_profile_v1": "memory_context_student"},
        operator_batch_audit={},
    )
    assert rep.get("ok_v1") is False
    miss = list(rep.get("missing_stages_v1") or [])
    assert "preflight_timeout_decision_snapshot_v1" in miss


@patch("renaissance_v4.game_theory.rm_preflight_wiring_v1.run_rm_preflight_decision_snapshot_v1")
def test_run_rm_preflight_propagates_decision_snapshot_failure(mock_snap):
    mock_snap.return_value = {
        "ok_v1": False,
        "scenario_id": "x",
        "trade_id": PREFLIGHT_DECISION_SNAPSHOT_TRADE_ID_V1,
        "seam_audit": None,
        "missing_stages_v1": ["preflight_decision_snapshot_packet_failed_v1"],
        "human_message_v1": "boom",
    }
    rep = run_rm_preflight_wiring_v1(
        scenarios=[{"manifest_path": "m.json", "scenario_id": "x"}],
        job_id="jid1",
        exam_run_contract_request_v1={
            "student_brain_profile_v1": "memory_context_llm_student",
        },
        operator_batch_audit={},
    )
    assert rep["ok_v1"] is False
    assert rep["status_v1"] == FAILED_PREFLIGHT_STATUS_V1
    mock_snap.assert_called_once()
