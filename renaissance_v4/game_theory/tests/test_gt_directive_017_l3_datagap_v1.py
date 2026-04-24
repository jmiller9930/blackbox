"""GT_DIRECTIVE_017 — L3 ``data_gaps[]`` matrix, ``GET /api/student-panel/run/<job_id>/l3``, validation rules."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
)
from renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1 import (
    SCHEMA_STUDENT_PANEL_L3_RESPONSE_V1,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    _L3_FLAG_EXPECT_DELIBERATION,
    _L3_FLAG_EXPECT_DOWNSTREAM,
    _L3_FLAG_EXPECT_GRADING,
    _L3_FLAG_EXPECT_PROCESS_SCORE,
    build_student_panel_l3_payload_v1,
    derive_l3_validation_data_gaps_v1,
)
from renaissance_v4.game_theory.web_app import create_app


def _minimal_rec(*, gaps: list[str], student_action: str = "NO_TRADE") -> dict:
    return {
        "schema": "student_decision_record_v1",
        "run_id": "j",
        "trade_id": "t",
        "student_action": student_action,
        "data_gaps": gaps,
    }


def test_l3_happy_path_empty_matrix() -> None:
    rec = _minimal_rec(gaps=[])
    entry = {
        "student_brain_profile_v1": "memory_context_stub_student",
        "skip_cold_baseline": True,
    }
    derived = derive_l3_validation_data_gaps_v1(rec=rec, entry=entry, replay_outcome={"metadata": {}})
    assert derived == []


def test_missing_process_score_gap_when_expected() -> None:
    rec = _minimal_rec(gaps=[])
    entry = {_L3_FLAG_EXPECT_PROCESS_SCORE: True, "student_l1_process_score_v1": None}
    g = derive_l3_validation_data_gaps_v1(rec=rec, entry=entry, replay_outcome=None)
    assert any(x.get("reason") == "student_l1_process_score_v1_missing" for x in g)
    assert any(x.get("producer") == "scorecard_writer" for x in g)


def test_missing_deliberation_gap_when_expected() -> None:
    rec = _minimal_rec(gaps=[])
    entry = {_L3_FLAG_EXPECT_DELIBERATION: True}
    g = derive_l3_validation_data_gaps_v1(rec=rec, entry=entry, replay_outcome=None)
    assert any(x.get("reason") == "exam_deliberation_not_on_parallel_scorecard_v1" for x in g)
    assert any(x.get("producer") == "exam_deliberation" for x in g)


def test_missing_downstream_frames_enter_when_expected() -> None:
    rec = _minimal_rec(gaps=[], student_action="ENTER")
    entry = {_L3_FLAG_EXPECT_DOWNSTREAM: True}
    g = derive_l3_validation_data_gaps_v1(
        rec=rec,
        entry=entry,
        replay_outcome={"metadata": {}},
    )
    assert any(x.get("reason") == "missing_downstream_frames_enter_parallel_v1" for x in g)
    assert any(x.get("producer") == "downstream_generator" for x in g)


def test_missing_baseline_anchor_gap() -> None:
    rec = _minimal_rec(gaps=[])
    entry = {
        "student_brain_profile_v1": "memory_context_stub_student",
        "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": "f" * 40},
        "skip_cold_baseline": False,
    }
    g = derive_l3_validation_data_gaps_v1(rec=rec, entry=entry, replay_outcome=None)
    assert any(x.get("reason") == "missing_baseline_anchor_when_required_v1" for x in g)


def test_missing_grading_when_expected() -> None:
    rec = _minimal_rec(gaps=[])
    entry = {_L3_FLAG_EXPECT_GRADING: True}
    g = derive_l3_validation_data_gaps_v1(rec=rec, entry=entry, replay_outcome=None)
    assert any(x.get("reason") == "missing_exam_grading_on_parallel_scorecard_v1" for x in g)


def test_llm_rejection_gap_producer_reason() -> None:
    rec = _minimal_rec(gaps=["student_store_record_missing_for_trade"])
    entry = {
        "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        "llm_student_output_rejections_v1": 1,
    }
    g = derive_l3_validation_data_gaps_v1(rec=rec, entry=entry, replay_outcome=None)
    row = next(x for x in g if x.get("reason") == "llm_student_output_rejected_pre_seal_v1")
    assert row.get("producer") == "student_llm"
    assert row.get("severity") == SEVERITY_WARNING


def test_llm_thesis_store_missing_critical_gap() -> None:
    from renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1 import build_structured_data_gaps_v1

    m = build_structured_data_gaps_v1(
        legacy_codes=["student_directional_thesis_store_missing_for_llm_profile_v1"]
    )
    assert len(m) == 1
    assert m[0].get("severity") == SEVERITY_CRITICAL
    assert m[0].get("producer") == "student_llm"
    assert m[0].get("reason") == "student_directional_thesis_store_missing_for_llm_profile_v1"


@pytest.fixture
def flask_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_http_l3_returns_200_and_data_gaps_array(flask_client) -> None:
    fake_rec = _minimal_rec(gaps=[])
    entry = {"job_id": "http017", "skip_cold_baseline": True}
    with (
        patch(
            "renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1.build_student_decision_record_v1",
            return_value=fake_rec,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1.find_scorecard_entry_by_job_id",
            return_value=entry,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1._load_replay_outcome_json_v1",
            return_value=({"trade_id": "t", "metadata": {}}, None),
        ),
    ):
        r = flask_client.get("/api/student-panel/run/http017/l3?trade_id=t")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("schema") == SCHEMA_STUDENT_PANEL_L3_RESPONSE_V1
    assert isinstance(body.get("data_gaps"), list)


def test_build_l3_payload_merge_legacy_and_derived() -> None:
    fake_rec = _minimal_rec(
        gaps=["student_store_record_missing_for_trade"],
        student_action="ENTER",
    )
    entry = {
        "job_id": "m017",
        "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        "llm_student_output_rejections_v1": 1,
        _L3_FLAG_EXPECT_PROCESS_SCORE: True,
        "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": "b" * 40},
        "skip_cold_baseline": False,
    }
    with (
        patch(
            "renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1.build_student_decision_record_v1",
            return_value=fake_rec,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1.find_scorecard_entry_by_job_id",
            return_value=entry,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1._load_replay_outcome_json_v1",
            return_value=({"trade_id": "t", "metadata": {}}, None),
        ),
    ):
        body = build_student_panel_l3_payload_v1("m017", "t")
    reasons = {x["reason"] for x in body["data_gaps"]}
    assert "student_store_record_missing_for_trade" in reasons
    assert "llm_student_output_rejected_pre_seal_v1" in reasons
    assert "student_l1_process_score_v1_missing" in reasons
    assert "missing_baseline_anchor_when_required_v1" in reasons


def test_fixture_files_parse() -> None:
    base = Path(__file__).resolve().parent / "fixtures"
    for name in (
        "gt_directive_017_l3_run_complete_v1.json",
        "gt_directive_017_l3_run_partial_v1.json",
        "gt_directive_017_l3_run_llm_rejection_v1.json",
    ):
        p = base / name
        assert p.is_file(), p
