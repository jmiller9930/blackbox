"""GT_DIRECTIVE_015 — exam run contract: brain profiles, legacy inputs, fingerprint, skip-cold."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.batch_scorecard import append_batch_scorecard_line, record_parallel_batch_finished
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1,
    LEGACY_STUDENT_REASONING_INPUT_MEMORY_CONTEXT_ONLY_V1,
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    STUDENT_EXECUTION_MODE_BASELINE_GATED_V1,
    STUDENT_EXECUTION_MODE_OFF_V1,
    STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1,
    STUDENT_FULL_CONTROL_STATUS_ENABLED_V1,
    STUDENT_FULL_CONTROL_STATUS_NOT_IMPLEMENTED_V1,
    STUDENT_REASONING_MODE_REPEAT_ANNA_V1,
    build_exam_run_line_meta_v1,
    find_prior_baseline_job_id_for_fingerprint_v1,
    normalize_student_reasoning_mode_v1,
    parse_exam_run_contract_request_v1,
    preview_run_config_fingerprint_sha256_40_v1,
    validate_student_reasoning_mode_v1,
)
from renaissance_v4.game_theory.web_app import _prepare_parallel_payload


_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "gt_directive_015_scorecard_fixture_lines.json"
)


def test_normalize_legacy_inputs_map_to_brain_profiles() -> None:
    assert (
        normalize_student_reasoning_mode_v1(LEGACY_STUDENT_REASONING_INPUT_MEMORY_CONTEXT_ONLY_V1)
        == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1
    )
    assert (
        normalize_student_reasoning_mode_v1("llm_qwen2_5_7b")
        == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    )
    assert (
        normalize_student_reasoning_mode_v1("llm_deepseek_r1_14b")
        == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    )


def test_validate_rejects_unknown_mode() -> None:
    assert validate_student_reasoning_mode_v1("not_a_mode") is not None


def test_parse_rejects_student_controlled_on_cold_baseline() -> None:
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
                "student_controlled_execution_v1": True,
            }
        }
    )
    assert out is None
    assert "student_controlled_execution_v1" in (err or "")


def test_parse_memory_profile_sets_baseline_gated_mode_when_controlled() -> None:
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                "student_controlled_execution_v1": True,
            }
        }
    )
    assert err is None and out is not None
    assert out["student_execution_mode_v1"] == STUDENT_EXECUTION_MODE_BASELINE_GATED_V1
    assert out["student_full_control_v1"] == STUDENT_FULL_CONTROL_STATUS_NOT_IMPLEMENTED_V1
    assert out["student_controlled_execution_v1"] is True


def test_parse_memory_profile_default_student_controlled_off() -> None:
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
            }
        }
    )
    assert err is None and out is not None
    assert out.get("student_controlled_execution_v1") is False
    assert out["student_execution_mode_v1"] == STUDENT_EXECUTION_MODE_OFF_V1


def test_parse_student_full_control_sets_enabled() -> None:
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                "student_controlled_execution_v1": True,
                "student_execution_mode_v1": "student_full_control",
            }
        }
    )
    assert err is None and out is not None
    assert out["student_execution_mode_v1"] == STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1
    assert out["student_full_control_v1"] == STUDENT_FULL_CONTROL_STATUS_ENABLED_V1


def test_build_exam_run_line_includes_execution_authority_v1() -> None:
    out, _ = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                "student_controlled_execution_v1": True,
            }
        }
    )
    assert out
    line = build_exam_run_line_meta_v1(
        request=out,
        operator_batch_audit={},
        fingerprint_sha256_40="a" * 40,
        job_id="j",
        student_seam_observability_v1={},
        batch_status="done",
    )
    assert line.get("execution_authority_v1") == "baseline_gated_student"
    assert "baseline-gated" in (line.get("student_lane_authority_truth_v1") or "").lower()


def test_build_exam_run_line_full_control_authority() -> None:
    out, _ = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                "student_controlled_execution_v1": True,
                "student_execution_mode_v1": "student_full_control",
            }
        }
    )
    assert out
    line = build_exam_run_line_meta_v1(
        request=out,
        operator_batch_audit={},
        fingerprint_sha256_40="b" * 40,
        job_id="job_fc",
        student_seam_observability_v1={},
        batch_status="done",
    )
    assert line.get("execution_authority_v1") == "student_full_control"
    assert line.get("student_full_control_v1") == STUDENT_FULL_CONTROL_STATUS_ENABLED_V1


def test_parse_student_decision_authority_mode_v1_valid() -> None:
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_reasoning_mode": STUDENT_REASONING_MODE_REPEAT_ANNA_V1,
                "student_decision_authority_mode_v1": "active",
            }
        }
    )
    assert err is None and out is not None
    assert out.get("student_decision_authority_mode_v1") == "active"


def test_parse_student_decision_authority_mode_v1_invalid() -> None:
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_reasoning_mode": STUDENT_REASONING_MODE_REPEAT_ANNA_V1,
                "student_decision_authority_mode_v1": "banana",
            }
        }
    )
    assert out is None
    assert err and "invalid student_decision_authority_mode_v1" in err


def test_parse_student_decision_authority_off_rejected_for_non_baseline() -> None:
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_reasoning_mode": STUDENT_REASONING_MODE_REPEAT_ANNA_V1,
                "student_decision_authority_mode_v1": "off",
            }
        }
    )
    assert out is None
    assert err and "STUDENT_DECISION_AUTHORITY_MANDATE_V1" in err


def test_parse_llm_profile_requires_http_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDENT_OLLAMA_BASE_URL", "ftp://invalid.example/no-http")
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
                "student_llm_v1": {"llm_model": "qwen2.5:7b"},
            }
        }
    )
    assert out is None and err == "ollama_base_url_invalid_or_unset_for_llm_assisted_mode"


def test_parse_llm_profile_rejects_non_approved_model() -> None:
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
                "student_llm_v1": {"llm_model": "qwen3-coder:30b"},
            }
        }
    )
    assert out is None
    assert err and "qwen2.5:7b" in (err or "")


def test_parse_legacy_llm_lane_infers_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_reasoning_mode": LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1,
            }
        }
    )
    assert err is None and out is not None
    assert out["student_brain_profile_v1"] == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    assert out["student_llm_v1"].get("llm_model") == "qwen2.5:7b"


def test_fixture_rows_use_brain_profiles() -> None:
    rows = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert len(rows) == 5
    profiles = {r.get("student_brain_profile_v1") or r.get("student_reasoning_mode") for r in rows}
    assert STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1 in profiles
    assert STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1 in profiles
    assert STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1 in profiles


def test_find_prior_anchor_on_temp_scorecard(tmp_path: Path) -> None:
    p = tmp_path / "sc.jsonl"
    fp = "b" * 40
    line = {
        "schema": "pattern_game_batch_scorecard_v1",
        "job_id": "anchor_job_gt015",
        "status": "done",
        "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": fp},
    }
    append_batch_scorecard_line(line, path=p)
    got = find_prior_baseline_job_id_for_fingerprint_v1(fp, scorecard_path=p)
    assert got == "anchor_job_gt015"


def test_record_parallel_merges_exam_line_meta(tmp_path: Path) -> None:
    req, _err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_reasoning_mode": STUDENT_REASONING_MODE_REPEAT_ANNA_V1,
                "skip_cold_baseline_if_anchor": False,
            }
        }
    )
    assert req is not None
    assert req["student_brain_profile_v1"] == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1
    meta = build_exam_run_line_meta_v1(
        request=req,
        operator_batch_audit={"context_signature_memory_mode": "read_write"},
        fingerprint_sha256_40="c" * 40,
        job_id="job_meta_1",
        student_seam_observability_v1={"shadow_student_enabled": True, "student_retrieval_matches": 0},
        batch_status="done",
    )
    timing = record_parallel_batch_finished(
        job_id="job_meta_1",
        started_at_utc="2026-04-24T12:00:00Z",
        start_unix=0.0,
        total_scenarios=1,
        workers_used=1,
        results=[
            {
                "ok": True,
                "scenario_id": "s1",
                "referee_session": "WIN",
                "summary": {"trades": 1, "win_rate": 1.0},
            }
        ],
        session_log_batch_dir=None,
        error=None,
        path=tmp_path / "sc2.jsonl",
        operator_batch_audit={
            "operator_recipe_id": "r1",
            "evaluation_window_effective_calendar_months": 12,
            "manifest_path_primary": "m.json",
            "policy_framework_path": "fw.json",
            "context_signature_memory_mode": "read_write",
        },
        exam_run_line_meta_v1=meta,
    )
    assert timing.get("student_brain_profile_v1") == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1
    assert timing.get("student_reasoning_mode") == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1
    assert timing.get("llm_used") is False


def test_prepare_parallel_fingerprint_preview_stable() -> None:
    data = {
        "operator_recipe_id": "custom",
        "scenarios_json": json.dumps(
            [
                {
                    "scenario_id": "z1",
                    "manifest_path": "renaissance_v4/manifests/foo.json",
                    "agent_explanation": {"hypothesis": "GT015 proof — minimal scenario for fingerprint preview."},
                }
            ]
        ),
        "evaluation_window_mode": "12",
    }
    prep = _prepare_parallel_payload(data)
    assert prep["ok"] is True
    scenarios = prep["scenarios"]
    oba = prep["operator_batch_audit"]
    fp1 = preview_run_config_fingerprint_sha256_40_v1(scenarios, oba)
    fp2 = preview_run_config_fingerprint_sha256_40_v1(scenarios, oba)
    assert fp1 == fp2 and len(fp1) == 40
