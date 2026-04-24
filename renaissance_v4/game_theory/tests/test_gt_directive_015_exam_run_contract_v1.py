"""GT_DIRECTIVE_015 — exam run contract: modes, fingerprint preview, skip-cold metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.batch_scorecard import append_batch_scorecard_line, record_parallel_batch_finished
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_REASONING_MODE_COLD_BASELINE_V1,
    STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1,
    STUDENT_REASONING_MODE_LLM_QWEN_V1,
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


def test_normalize_legacy_aliases() -> None:
    assert normalize_student_reasoning_mode_v1("memory_context_only") == STUDENT_REASONING_MODE_REPEAT_ANNA_V1
    assert normalize_student_reasoning_mode_v1("llm_qwen2_5_7b") == STUDENT_REASONING_MODE_LLM_QWEN_V1
    assert normalize_student_reasoning_mode_v1("llm_deepseek_r1_14b") == STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1


def test_validate_rejects_unknown_mode() -> None:
    assert validate_student_reasoning_mode_v1("not_a_mode") is not None


def test_parse_llm_requires_http_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "ftp://invalid.example/no-http")
    out, err = parse_exam_run_contract_request_v1(
        {"exam_run_contract_v1": {"student_reasoning_mode": STUDENT_REASONING_MODE_LLM_QWEN_V1}}
    )
    assert out is None and err == "ollama_base_url_invalid_or_unset_for_llm_assisted_mode"


def test_fixture_has_five_distinct_lanes() -> None:
    rows = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert len(rows) == 5
    modes = {r["student_reasoning_mode"] for r in rows}
    assert STUDENT_REASONING_MODE_COLD_BASELINE_V1 in modes
    assert STUDENT_REASONING_MODE_REPEAT_ANNA_V1 in modes
    assert STUDENT_REASONING_MODE_LLM_QWEN_V1 in modes
    assert STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1 in modes


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
    assert timing.get("student_reasoning_mode") == STUDENT_REASONING_MODE_REPEAT_ANNA_V1
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
