"""
GT_DIRECTIVE_015 — HTTP: POST /api/run-parallel with exam_run_contract_v1; scorecard metadata captured.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    STUDENT_REASONING_MODE_LLM_QWEN_V1,
)
from renaissance_v4.game_theory.web_app import create_app


@pytest.fixture
def flask_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _minimal_outcome_json() -> dict:
    return {
        "trade_id": "tr_gt015_http",
        "symbol": "SOLUSDT",
        "direction": "long",
        "entry_time": 1_700_000_000_000,
        "exit_time": 1_700_000_360_000,
        "entry_price": 100.0,
        "exit_price": 101.0,
        "pnl": 1.0,
        "mae": 0.5,
        "mfe": 2.0,
        "exit_reason": "take_profit",
        "metadata": {},
    }


def _fake_rm_preflight_pass_v1() -> dict:
    """Web tests mock the parallel batch; RM preflight must be stubbed the same way."""
    return {
        "schema": "rm_preflight_wiring_audit_v1",
        "ok_v1": True,
        "skipped_v1": False,
        "status_v1": "passed_rm_preflight_wiring_v1",
        "missing_stages_v1": [],
        "memory_sink_event_count_v1": 0,
    }


def _fake_student_rm_trace_proof_ok_v1() -> dict:
    """Stub post-seam JSONL proof — these tests do not write a real learning trace file."""
    return {
        "schema": "student_reasoning_model_trace_proof_v1",
        "ok_v1": True,
        "skipped_v1": False,
        "errors_v1": [],
        "sealed_trade_count_v1": 1,
        "student_decision_authority_event_count_v1": 1,
        "counts_match_v1": True,
    }


def _fake_terminal_integrity_ok_for_job_v1() -> dict:
    """Stub file-backed terminal counts — GT015 mocks seam/trace without writing JSONL."""
    return {
        "schema": "learning_trace_terminal_integrity_v1",
        "student_decision_authority_v1_count": 1,
        "student_output_sealed_count": 1,
        "integrity_ok": True,
        "lines_matched_job": 2,
        "trace_file_exists": True,
    }


def _fake_execute_student_behavior_probe_pass_v1(*_a: object, **_kw: object) -> tuple[None, dict]:
    """Avoid real subprocess probe — GT015 exercises HTTP + mocked parallel/seam only."""
    return (
        None,
        {
            "probe_summary_v1": {
                "authority_count_v1": 1,
                "sealed_count_v1": 1,
                "rejection_count_v1": 0,
                "contract_violation_count_v1": 0,
            },
            "probe_timeout_v1": False,
            "probe_wall_clock_s_v1": 0.01,
            "probe_wall_limit_s_v1": 120.0,
        },
    )


def _fake_parallel_row() -> dict:
    return {
        "ok": True,
        "scenario_id": "s_gt015_http",
        "referee_session": "WIN",
        "summary": {
            "trades": 1,
            "win_rate": 100.0,
            "cumulative_pnl": 1.0,
            "learning_run_audit_v1": {
                "decision_windows_total": 4,
                "bars_processed": 40,
                "learning_engaged_v1": False,
            },
        },
        "learning_run_audit_v1": {
            "decision_windows_total": 4,
            "bars_processed": 40,
            "learning_engaged_v1": False,
        },
        "replay_outcomes_json": [_minimal_outcome_json()],
    }


@patch(
    "renaissance_v4.game_theory.student_behavior_probe_v1.execute_student_behavior_probe_v1",
    new=_fake_execute_student_behavior_probe_pass_v1,
)
def test_post_run_parallel_blocking_writes_lane_metadata(
    flask_client, tmp_path: Path
) -> None:
    """POST /api/run-parallel (same contract as /start) — scorecard line gets lane fields."""
    import renaissance_v4.game_theory.web_app as web_app_mod

    last_meta: dict = {}

    def fake_record(*, exam_run_line_meta_v1=None, path=None, **kwargs):
        if exam_run_line_meta_v1 is not None:
            last_meta.clear()
            last_meta.update(exam_run_line_meta_v1)
        from renaissance_v4.game_theory.batch_scorecard import record_parallel_batch_finished as real

        return real(**{**kwargs, "path": tmp_path / "sc_http.jsonl", "exam_run_line_meta_v1": exam_run_line_meta_v1})

    fake_seam = {
        "schema": "student_loop_seam_audit_v1",
        "student_seam_stop_reason_v1": "completed_all_trades_v1",
        "student_decision_authority_mandate_enforced_v1": True,
        "student_learning_rows_appended": 0,
        "student_retrieval_matches": 0,
        "student_output_fingerprint": None,
        "shadow_student_enabled": False,
        "student_llm_execution_v1": {
            "schema": "student_llm_execution_v1",
            "student_brain_profile_echo_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
            "student_reasoning_mode_echo": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
            "model_resolved": "qwen2.5:7b",
            "base_url_resolved": "http://127.0.0.1:11434",
            "resolved_model": "qwen2.5:7b",
            "ollama_base_url_used": "http://127.0.0.1:11434",
            "ollama_any_attempt": True,
            "ollama_trades_attempted": 1,
            "ollama_trades_succeeded": 1,
            "prompt_version_resolved": "gt015_http_test_v1",
        },
    }

    with patch.object(web_app_mod, "record_parallel_batch_finished", side_effect=fake_record):
        with patch(
            "renaissance_v4.game_theory.rm_preflight_wiring_v1.run_rm_preflight_wiring_v1",
            return_value=_fake_rm_preflight_pass_v1(),
        ):
            with patch(
                "renaissance_v4.game_theory.web_app.run_scenarios_parallel",
                return_value=[_fake_parallel_row()],
            ):
                with patch(
                    "renaissance_v4.game_theory.web_app.student_loop_seam_after_parallel_batch_v1",
                    return_value=fake_seam,
                ):
                    with patch(
                        "renaissance_v4.game_theory.web_app.promote_groundhog_bundle_from_parallel_scenarios_v1",
                        return_value={},
                    ):
                        with patch(
                            "renaissance_v4.game_theory.web_app.validate_reference_comparison_batch_results",
                            return_value=None,
                        ):
                            with patch(
                                "renaissance_v4.game_theory.web_app.prune_pml_runtime_batch_dirs",
                                return_value=None,
                            ):
                                with patch(
                                    "renaissance_v4.game_theory.tools.student_reasoning_model_trace_proof_v1.validate_student_reasoning_model_trace_for_job_v1",
                                    return_value=_fake_student_rm_trace_proof_ok_v1(),
                                ):
                                    with patch(
                                        "renaissance_v4.game_theory.learning_trace_events_v1.count_learning_trace_terminal_integrity_v1",
                                        return_value=_fake_terminal_integrity_ok_for_job_v1(),
                                    ):
                                        r = flask_client.post(
                                            "/api/run-parallel",
                                            json={
                                                "operator_recipe_id": "custom",
                                                "scenarios_json": '[{"scenario_id":"s_gt015_http","manifest_path":"renaissance_v4/configs/manifests/baseline_v1_recipe.json","agent_explanation":{"hypothesis":"GT015 HTTP test"}}]',
                                                "evaluation_window_mode": "12",
                                                "exam_run_contract_v1": {
                                                    "student_reasoning_mode": STUDENT_REASONING_MODE_LLM_QWEN_V1,
                                                    "skip_cold_baseline_if_anchor": True,
                                                    "prompt_version": "gt015_http_test_v1",
                                                    "retrieved_context_ids": [],
                                                },
                                            },
                                        )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body.get("ok") is True
    assert last_meta.get("student_brain_profile_v1") == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    assert last_meta.get("student_reasoning_mode") == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    assert last_meta.get("llm_model") == "qwen2.5:7b"
    assert last_meta.get("resolved_model") == "qwen2.5:7b"
    assert "172.20.1.66" not in (last_meta.get("ollama_base_url_used") or "")
    assert last_meta.get("student_llm_execution_v1", {}).get("ollama_trades_succeeded") == 1


@patch(
    "renaissance_v4.game_theory.student_behavior_probe_v1.execute_student_behavior_probe_v1",
    new=_fake_execute_student_behavior_probe_pass_v1,
)
def test_post_run_parallel_start_returns_200_with_exam_contract(
    flask_client, tmp_path: Path
) -> None:
    """POST /api/run-parallel/start — body includes exam_run_contract_v1; job completes inline (Thread patched)."""
    import threading

    import renaissance_v4.game_theory.web_app as web_app_mod

    class _ImmediateThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._target = target

        def start(self) -> None:
            if self._target:
                self._target()

    last_meta: dict = {}

    def fake_record(*, exam_run_line_meta_v1=None, path=None, **kwargs):
        if exam_run_line_meta_v1 is not None:
            last_meta.clear()
            last_meta.update(exam_run_line_meta_v1)
        from renaissance_v4.game_theory.batch_scorecard import record_parallel_batch_finished as real

        return real(**{**kwargs, "path": tmp_path / "sc_start.jsonl", "exam_run_line_meta_v1": exam_run_line_meta_v1})

    fake_seam = {
        "schema": "student_loop_seam_audit_v1",
        "student_seam_stop_reason_v1": "completed_all_trades_v1",
        "student_decision_authority_mandate_enforced_v1": True,
        "student_learning_rows_appended": 0,
        "student_retrieval_matches": 0,
        "student_output_fingerprint": "ab" * 32,
        "shadow_student_enabled": True,
        "student_llm_execution_v1": {
            "schema": "student_llm_execution_v1",
            "student_brain_profile_echo_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
            "student_reasoning_mode_echo": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
            "model_resolved": "qwen2.5:7b",
            "base_url_resolved": "http://127.0.0.1:11434",
            "resolved_model": "qwen2.5:7b",
            "ollama_base_url_used": "http://127.0.0.1:11434",
            "ollama_any_attempt": True,
            "ollama_trades_attempted": 1,
            "ollama_trades_succeeded": 1,
            "prompt_version_resolved": "gt015_start_test_v1",
        },
    }

    with patch.object(threading, "Thread", _ImmediateThread):
        with patch.object(web_app_mod, "record_parallel_batch_finished", side_effect=fake_record):
            with patch(
                "renaissance_v4.game_theory.rm_preflight_wiring_v1.run_rm_preflight_wiring_v1",
                return_value=_fake_rm_preflight_pass_v1(),
            ):
                with patch(
                    "renaissance_v4.game_theory.web_app.run_scenarios_parallel",
                    return_value=[_fake_parallel_row()],
                ):
                    with patch(
                        "renaissance_v4.game_theory.web_app.student_loop_seam_after_parallel_batch_v1",
                        return_value=fake_seam,
                    ):
                        with patch(
                            "renaissance_v4.game_theory.web_app.promote_groundhog_bundle_from_parallel_scenarios_v1",
                            return_value={},
                        ):
                            with patch(
                                "renaissance_v4.game_theory.web_app.validate_reference_comparison_batch_results",
                                return_value=None,
                            ):
                                with patch(
                                    "renaissance_v4.game_theory.web_app.prune_pml_runtime_batch_dirs",
                                    return_value=None,
                                ):
                                    with patch(
                                        "renaissance_v4.game_theory.tools.student_reasoning_model_trace_proof_v1.validate_student_reasoning_model_trace_for_job_v1",
                                        return_value=_fake_student_rm_trace_proof_ok_v1(),
                                    ):
                                        with patch(
                                            "renaissance_v4.game_theory.learning_trace_events_v1.count_learning_trace_terminal_integrity_v1",
                                            return_value=_fake_terminal_integrity_ok_for_job_v1(),
                                        ):
                                            r = flask_client.post(
                                                "/api/run-parallel/start",
                                                json={
                                                    "operator_recipe_id": "custom",
                                                    "scenarios_json": '[{"scenario_id":"s_gt015_http","manifest_path":"renaissance_v4/configs/manifests/baseline_v1_recipe.json","agent_explanation":{"hypothesis":"GT015 start test"}}]',
                                                    "evaluation_window_mode": "12",
                                                    "exam_run_contract_v1": {
                                                        "student_reasoning_mode": STUDENT_REASONING_MODE_LLM_QWEN_V1,
                                                        "prompt_version": "gt015_start_test_v1",
                                                    },
                                                },
                                            )
    assert r.status_code == 200, r.get_data(as_text=True)
    st = r.get_json()
    assert st.get("ok") is True
    jid = st.get("job_id")
    assert jid
    pr = flask_client.get(f"/api/run-parallel/status/{jid}")
    assert pr.status_code == 200
    pj = pr.get_json()
    assert pj.get("status") == "done"
    assert last_meta.get("student_brain_profile_v1") == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    assert last_meta.get("student_reasoning_mode") == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
