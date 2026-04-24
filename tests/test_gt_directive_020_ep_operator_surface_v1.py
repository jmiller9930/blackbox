"""GT_DIRECTIVE_020 — E/P on L1 road API, road_by_job_id merge, Ask DATA dictionary topic."""

from __future__ import annotations

from renaissance_v4.game_theory.ask_data_system_dictionary_v1 import system_dictionary_context_v1
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
)
from renaissance_v4.game_theory.student_panel_l1_road_v1 import build_l1_road_payload_v1


def _line(
    job_id: str,
    fp: str,
    profile: str,
    *,
    exam_e: float | None = None,
    exam_p: float | None = None,
    exam_pass: bool | None = None,
    exp: float = 0.01,
) -> dict:
    row: dict = {
        "job_id": job_id,
        "status": "done",
        "started_at_utc": "2026-04-21T12:00:00Z",
        "expectancy_per_trade": exp,
        "referee_win_pct": 50.0,
        "batch_trade_win_pct": 50.0,
        "batch_trades_count": 5,
        "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": fp},
        "student_brain_profile_v1": profile,
    }
    if exam_e is not None:
        row["exam_e_score_v1"] = exam_e
    if exam_p is not None:
        row["exam_p_score_v1"] = exam_p
    if exam_pass is not None:
        row["exam_pass_v1"] = exam_pass
    if exam_e is not None:
        row["l1_e_value_source_v1"] = "exam_pack_grading_v1"
    else:
        row["l1_e_value_source_v1"] = "expectancy_per_trade_proxy_v1"
    if exam_p is not None:
        row["l1_p_value_source_v1"] = "exam_pack_grading_v1"
    else:
        row["l1_p_value_source_v1"] = "data_gap"
    return row


def test_l1_road_group_exam_aggregates_and_road_by_job_exam_fields() -> None:
    fp = "fp_gt020______________________________"
    lines = [
        _line(
            "anchor1",
            fp,
            STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
            exam_e=0.1,
            exam_p=0.2,
            exam_pass=True,
            exp=0.99,
        ),
        _line(
            "mem1",
            fp,
            STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
            exam_e=0.5,
            exam_p=0.6,
            exam_pass=True,
            exp=0.1,
        ),
        _line(
            "mem2",
            fp,
            STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
            exam_e=None,
            exam_p=None,
            exam_pass=None,
            exp=0.2,
        ),
    ]
    payload = build_l1_road_payload_v1(lines=lines)
    road = payload.get("road_by_job_id_v1") or {}
    m = road.get("mem1") or {}
    assert m.get("exam_e_score_v1") == 0.5
    assert m.get("exam_p_score_v1") == 0.6
    assert m.get("exam_pass_v1") is True
    assert m.get("l1_e_value_source_v1") == "exam_pack_grading_v1"
    assert m.get("l1_e_scalar_v1") == 0.5

    groups = payload.get("groups") or []
    mem_groups = [g for g in groups if (g.get("group_key") or {}).get("student_brain_profile_v1") == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1]
    assert len(mem_groups) == 1
    g = mem_groups[0]
    assert g.get("group_exam_graded_run_count_v1") == 1
    assert g.get("group_exam_pass_count_v1") == 1
    assert g.get("group_avg_exam_e_score_v1") == 0.5
    assert g.get("group_avg_exam_p_score_v1") == 0.6


def test_system_dictionary_includes_gt020_exam_ep_topic() -> None:
    d = system_dictionary_context_v1()
    topics = (d.get("topics") or {})
    assert "exam_ep_student_panel_gt020" in topics
    assert "exam_e_score_v1" in topics["exam_ep_student_panel_gt020"]
