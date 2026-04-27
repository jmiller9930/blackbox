"""Governed Student Decision Authority (shadow / active)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.student_proctor.lifecycle_deterministic_learning_026c_v1 import (
    FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C,
)
from renaissance_v4.game_theory.student_proctor import student_decision_authority_v1 as m


def _ere(action: str, conf: float = 0.5, router: dict | None = None) -> dict:
    out = {
        "decision_synthesis_v1": {"action": action},
        "confidence_01": conf,
        "entry_reasoning_eval_digest_v1": "abc" * 20,
    }
    if router is not None:
        out["reasoning_router_decision_v1"] = router
    return out


def _slice(score: float, rid: str = "r1", pk: str = "SOL:5:long:target") -> dict:
    return {
        "schema": "retrieved_lifecycle_deterministic_learning_slice_026c_v1",
        "record_id_026c": rid,
        "pattern_key_026c_v1": pk,
        "overall_score_01": score,
        "decay_weight_01": 0.5,
    }


@patch.dict(os.environ, {"PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1": "shadow"}, clear=False)
def test_shadow_suppress_entry_when_026c_weak():
    ere = _ere("enter_long")
    pkt = {FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C: [_slice(0.35), _slice(0.38, rid="r2")]}
    pl = m.compute_student_decision_authority_payload_v1(
        ere=ere, pkt=pkt, unified_router_enabled=False, exam_run_contract_request_v1=None
    )
    assert pl["authority_mode_v1"] == "shadow"
    assert pl["authority_applied_v1"] is False
    assert pl["authority_would_apply_v1"] is True
    assert pl["authority_action_v1"] == "shadow_suppress_entry_026c_weak_evidence_v1"
    assert pl["before_decision_snapshot_v1"]["decision_action_v1"] == "enter_long"
    assert pl["after_decision_snapshot_v1"]["decision_action_v1"] == "no_trade"
    assert pl["retrieved_026c_record_ids_v1"] == ["r1", "r2"]


@patch.dict(os.environ, {"PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1": "shadow"}, clear=False)
def test_shadow_promote_entry_when_026c_strong_short():
    ere = _ere("no_trade")
    pkt = {FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C: [_slice(0.9, pk="X:5:short:stop")]}
    pl = m.compute_student_decision_authority_payload_v1(
        ere=ere, pkt=pkt, unified_router_enabled=False, exam_run_contract_request_v1=None
    )
    assert pl["authority_would_apply_v1"] is True
    assert pl["after_decision_snapshot_v1"]["decision_action_v1"] == "enter_short"


@patch.dict(os.environ, {"PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1": "active"}, clear=False)
def test_active_patches_ere_when_router_present():
    router_doc = {"schema": "reasoning_router_decision_v1", "final_route_v1": "local_only"}
    ere = _ere("enter_long", router=router_doc)
    pkt = {FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C: [_slice(0.35)]}
    pl = m.compute_student_decision_authority_payload_v1(
        ere=ere,
        pkt=pkt,
        unified_router_enabled=True,
        exam_run_contract_request_v1=None,
    )
    assert pl["authority_would_apply_v1"] is True
    out = m.maybe_apply_student_decision_authority_to_ere_v1(ere=ere, payload=pl, exam_run_contract_request_v1=None)
    assert out["authority_applied_v1"] is True
    assert (ere.get("decision_synthesis_v1") or {}).get("action") == "no_trade"


@patch.dict(os.environ, {"PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1": "active"}, clear=False)
def test_active_blocked_without_router_when_unified_enabled():
    ere = _ere("enter_long")
    pkt = {FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C: [_slice(0.35)]}
    pl = m.compute_student_decision_authority_payload_v1(
        ere=ere, pkt=pkt, unified_router_enabled=True, exam_run_contract_request_v1=None
    )
    assert pl["authority_would_apply_v1"] is False
    assert "active_requires_router_decision_when_router_enabled_v1" in pl["authority_reason_codes_v1"]


def test_exam_contract_overrides_env():
    with patch.dict(os.environ, {"PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1": "off"}, clear=False):
        assert m.student_decision_authority_mode_v1({"student_decision_authority_mode_v1": "shadow"}) == "shadow"


@patch.dict(
    os.environ,
    {
        "PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1": "shadow",
        "PATTERN_GAME_LEARNING_TRACE_EVENTS": "1",
    },
    clear=False,
)
def test_run_for_trade_emits_trace(monkeypatch):
    calls: list[dict] = []

    def _capture(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_trace_instrumentation_v1.append_learning_trace_event_from_kwargs_v1",
        _capture,
    )
    ere = _ere("enter_long")
    pkt = {FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C: [_slice(0.35)]}
    m.run_student_decision_authority_for_trade_v1(
        job_id="j1",
        fingerprint="fp",
        scenario_id="s1",
        trade_id="t1",
        ere=ere,
        pkt=pkt,
        unified_router_enabled=False,
        exam_run_contract_request_v1=None,
    )
    assert calls
    assert calls[0].get("stage") == "student_decision_authority_v1"
    ev = (calls[0].get("evidence_payload") or {}).get("student_decision_authority_v1") or {}
    assert ev.get("authority_mode_v1") == "shadow"


def test_mandate_raises_when_learning_trace_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_LEARNING_TRACE_EVENTS", "0")
    monkeypatch.setenv("PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1", "shadow")
    ere = _ere("enter_long")
    pkt = {FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C: [_slice(0.35)]}
    with pytest.raises(RuntimeError, match="STUDENT_DECISION_AUTHORITY_MANDATE_V1"):
        m.run_student_decision_authority_for_trade_v1(
            job_id="job_m",
            fingerprint="fp",
            scenario_id="s",
            trade_id="t",
            ere=ere,
            pkt=pkt,
            unified_router_enabled=False,
            exam_run_contract_request_v1=None,
            mandate_active_v1=True,
        )


def test_mandate_persists_trace_and_sets_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lt = tmp_path / "learning_trace_events_v1.jsonl"
    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_trace_events_v1.default_learning_trace_events_jsonl",
        lambda: lt,
    )
    monkeypatch.setenv("PATTERN_GAME_LEARNING_TRACE_EVENTS", "1")
    monkeypatch.setenv("PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1", "shadow")
    ere = _ere("no_trade")
    pkt = {FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C: [_slice(0.9)]}
    m.run_student_decision_authority_for_trade_v1(
        job_id="job_live_proof",
        fingerprint="a" * 40,
        scenario_id="sc1",
        trade_id="tr1",
        ere=ere,
        pkt=pkt,
        unified_router_enabled=False,
        exam_run_contract_request_v1=None,
        mandate_active_v1=True,
    )
    bind = ere.get("student_decision_authority_binding_v1")
    assert isinstance(bind, dict)
    assert bind.get("learning_trace_persisted_v1") is True
    assert bind.get("decision_source_v1") == m.DECISION_SOURCE_REASONING_MODEL_V1
    assert lt.is_file()
    row = json.loads(lt.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row.get("stage") == "student_decision_authority_v1"
    assert row.get("job_id") == "job_live_proof"
    pl = (row.get("evidence_payload") or {}).get("student_decision_authority_v1") or {}
    assert pl.get("authority_mode_v1") == "shadow"
    assert "before_decision_snapshot_v1" in pl
    assert "after_decision_snapshot_v1" in pl
    assert "referee_safety_check_v1" in pl


def test_validate_mandate_preconditions_trace_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_LEARNING_TRACE_EVENTS", "0")
    errs = m.validate_student_decision_authority_mandate_preconditions_v1(
        exam_run_contract_request_v1=None,
        job_id="jid",
        student_brain_profile_v1="memory_context_student",
    )
    assert errs and any("PATTERN_GAME_LEARNING_TRACE_EVENTS" in x for x in errs)


def test_validate_mandate_preconditions_empty_job_id() -> None:
    errs = m.validate_student_decision_authority_mandate_preconditions_v1(
        exam_run_contract_request_v1=None,
        job_id="   ",
        student_brain_profile_v1="memory_context_student",
    )
    assert errs and any("job_id" in x for x in errs)


def test_validate_mandate_baseline_profile_no_errors() -> None:
    assert (
        m.validate_student_decision_authority_mandate_preconditions_v1(
            exam_run_contract_request_v1=None,
            job_id="",
            student_brain_profile_v1="baseline_no_memory_no_llm",
        )
        == []
    )


@patch.dict(os.environ, {"PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1": "shadow"}, clear=False)
def test_mandate_raises_when_emit_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_emit(**_kwargs):
        return False

    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_trace_instrumentation_v1.emit_student_decision_authority_v1",
        _no_emit,
        raising=True,
    )
    ere = _ere("enter_long")
    pkt = {FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C: [_slice(0.35)]}
    with pytest.raises(RuntimeError, match="not persisted"):
        m.run_student_decision_authority_for_trade_v1(
            job_id="j2",
            fingerprint="fp",
            scenario_id="s",
            trade_id="t",
            ere=ere,
            pkt=pkt,
            unified_router_enabled=False,
            exam_run_contract_request_v1=None,
            mandate_active_v1=True,
        )
