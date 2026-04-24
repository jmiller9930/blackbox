"""GT_DIRECTIVE_019 — exam E/P on scorecard, L1 preference, D11 API, L3 grading gap."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.exam_ep_scorecard_denorm_v1 import (
    annotate_l1_ep_value_sources_v1,
)
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
)
from renaissance_v4.game_theory.exam_state_machine_v1 import ExamPhase
from renaissance_v4.game_theory.student_panel_d11 import build_d11_run_rows_v1
from renaissance_v4.game_theory.student_panel_l1_road_v1 import (
    build_l1_road_payload_v1,
    line_e_value_for_l1_v1,
    line_p_value_for_l1_v1,
)
from renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1 import (
    PRODUCER_GRADING_SERVICE,
    SEVERITY_CRITICAL,
    derive_l3_validation_data_gaps_v1,
)

_FP40 = "mixed_fp_gt019________________________"


def _done_line(
    *,
    job_id: str,
    profile: str,
    expectancy: float,
    started: str = "2026-04-20T12:00:00Z",
    exam_e: float | None = None,
    exam_p: float | None = None,
    proc_proxy: float | None = None,
) -> dict:
    row: dict = {
        "job_id": job_id,
        "status": "done",
        "started_at_utc": started,
        "batch_trade_win_pct": 50.0,
        "batch_trades_count": 10,
        "expectancy_per_trade": expectancy,
        "student_output_fingerprint": "x",
        "scenario_id": "scen_a",
        "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
        "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": _FP40},
        "student_brain_profile_v1": profile,
        "referee_win_pct": 50.0,
    }
    if exam_e is not None:
        row["exam_e_score_v1"] = exam_e
    if exam_p is not None:
        row["exam_p_score_v1"] = exam_p
    if proc_proxy is not None:
        row["student_l1_process_score_v1"] = proc_proxy
    annotate_l1_ep_value_sources_v1(row)
    return row


def test_line_e_prefers_exam_over_expectancy() -> None:
    row = {"expectancy_per_trade": 0.01, "exam_e_score_v1": 0.88}
    assert line_e_value_for_l1_v1(row) == pytest.approx(0.88)


def test_line_e_fallback_expectancy() -> None:
    row = {"expectancy_per_trade": 0.03}
    assert line_e_value_for_l1_v1(row) == pytest.approx(0.03)


def test_line_p_prefers_exam_over_process_proxy() -> None:
    row = {"exam_p_score_v1": 0.77, "student_l1_process_score_v1": 0.11}
    assert line_p_value_for_l1_v1(row) == pytest.approx(0.77)


def test_line_p_process_proxy_when_no_exam_p() -> None:
    row = {"student_l1_process_score_v1": 0.55}
    assert line_p_value_for_l1_v1(row) == pytest.approx(0.55)


def test_line_p_null_without_either() -> None:
    assert line_p_value_for_l1_v1({}) is None


def test_annotate_l1_sources_exam_vs_proxy() -> None:
    r1: dict = {"exam_e_score_v1": 1.0, "exam_p_score_v1": 0.5}
    annotate_l1_ep_value_sources_v1(r1)
    assert r1["l1_e_value_source_v1"] == "exam_pack_grading_v1"
    assert r1["l1_p_value_source_v1"] == "exam_pack_grading_v1"

    r2: dict = {"expectancy_per_trade": 0.1}
    annotate_l1_ep_value_sources_v1(r2)
    assert r2["l1_e_value_source_v1"] == "expectancy_per_trade_proxy_v1"
    assert r2["l1_p_value_source_v1"] == "data_gap"


def test_l1_mixed_group_carries_both_e_sources() -> None:
    lines = [
        _done_line(
            job_id="anchor_baseline",
            profile=STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
            expectancy=0.1,
            started="2026-04-20T11:00:00Z",
        ),
        _done_line(
            job_id="graded_mem",
            profile=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
            expectancy=0.99,
            exam_e=0.5,
            exam_p=0.6,
            started="2026-04-20T12:00:00Z",
        ),
        _done_line(
            job_id="proxy_mem",
            profile=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
            expectancy=0.2,
            started="2026-04-20T13:00:00Z",
        ),
    ]
    payload = build_l1_road_payload_v1(lines=lines)
    groups = payload.get("groups") or []
    mem_groups = [g for g in groups if (g.get("group_key") or {}).get("student_brain_profile_v1") == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1]
    assert len(mem_groups) == 1
    g = mem_groups[0]
    assert set(g.get("l1_e_value_sources_v1") or []) == {
        "exam_pack_grading_v1",
        "expectancy_per_trade_proxy_v1",
    }
    # Avg E uses 0.5 and 0.2, not 0.99 and 0.2
    assert g.get("avg_e_expectancy_per_trade") == pytest.approx(0.35)


def test_d11_run_rows_include_exam_and_sources() -> None:
    row = _done_line(
        job_id="d11_exam",
        profile=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        expectancy=0.1,
        exam_e=0.2,
        exam_p=0.3,
    )
    row["exam_pass_v1"] = True
    out = build_d11_run_rows_v1([row])
    assert len(out) == 1
    r = out[0]
    assert r["exam_e_score_v1"] == pytest.approx(0.2)
    assert r["exam_p_score_v1"] == pytest.approx(0.3)
    assert r["exam_pass_v1"] is True
    assert r["l1_e_value_source_v1"] == "exam_pack_grading_v1"


def test_d11_outcome_improved_uses_l1_e_scalar() -> None:
    fp = "out_imp_gt019_________________________"
    older = _done_line(
        job_id="old",
        profile=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        expectancy=0.05,
        exam_e=0.1,
        started="2026-04-20T10:00:00Z",
    )
    older["memory_context_impact_audit_v1"] = {"run_config_fingerprint_sha256_40": fp}
    newer = _done_line(
        job_id="new",
        profile=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        expectancy=0.01,
        exam_e=0.4,
        started="2026-04-20T11:00:00Z",
    )
    newer["memory_context_impact_audit_v1"] = {"run_config_fingerprint_sha256_40": fp}
    rows = build_d11_run_rows_v1([newer, older])
    by_id = {str(x["run_id"]): x for x in rows}
    assert by_id["new"]["outcome_improved"] == "YES"


def test_derive_l3_exam_grading_missing_for_scored_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeU:
        exam_pack_id = "pack_x"
        exam_pack_version = "1"
        phase = ExamPhase.COMPLETE
        enter = True

    def fake_get_exam(uid: str):
        return FakeU() if uid == "exam-unit-miss" else None

    def fake_timeline(uid: str):
        return {"decision_frames": [{"frame_type": "opening", "payload": {}}]}

    def fake_delib(uid: str):
        return {"schema": "exam_deliberation_payload_v1", "hypotheses": {}}

    class _Cfg:
        pass

    def fake_cfg(pid: str, ver: str):
        return _Cfg()

    monkeypatch.setattr(
        "renaissance_v4.game_theory.exam_state_machine_v1.get_exam_unit_v1",
        fake_get_exam,
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.exam_decision_frame_schema_v1.get_committed_timeline_v1",
        fake_timeline,
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.exam_deliberation_capture_v1.get_frame0_deliberation_v1",
        fake_delib,
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.exam_grading_service_v1.get_exam_pack_grading_config_v1",
        fake_cfg,
    )

    entry = {
        "job_id": "job-miss",
        "status": "done",
        "exam_unit_id": "exam-unit-miss",
        "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    }
    gaps = derive_l3_validation_data_gaps_v1(rec={"data_gaps": []}, entry=entry, replay_outcome=None)
    reasons = [str(g.get("reason")) for g in gaps]
    assert "exam_grading_missing_for_scored_run_v1" in reasons
    row = next(g for g in gaps if g.get("reason") == "exam_grading_missing_for_scored_run_v1")
    assert row.get("producer") == PRODUCER_GRADING_SERVICE
    assert row.get("severity") == SEVERITY_CRITICAL


def test_derive_l3_no_gap_when_exam_e_present() -> None:
    entry = {
        "job_id": "job-ok",
        "status": "done",
        "exam_unit_id": "any",
        "exam_e_score_v1": 0.33,
        "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    }
    gaps = derive_l3_validation_data_gaps_v1(rec={"data_gaps": []}, entry=entry, replay_outcome=None)
    reasons = [str(g.get("reason")) for g in gaps]
    assert "exam_grading_missing_for_scored_run_v1" not in reasons
