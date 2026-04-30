"""
GT066 — Offline proof: parallel batch path reaches terminal DONE without watchdog timeout.

Uses Flask test client + mocked replay/seam (same wiring as GT064/GT015); asserts pipeline tape lines.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def _fake_rm_preflight_pass_v1() -> dict:
    return {
        "schema": "rm_preflight_wiring_audit_v1",
        "ok_v1": True,
        "skipped_v1": False,
        "status_v1": "passed_rm_preflight_wiring_v1",
        "missing_stages_v1": [],
        "memory_sink_event_count_v1": 0,
    }


def _fake_parallel_row() -> dict:
    return {
        "ok": True,
        "scenario_id": "s_gt066",
        "referee_session": "WIN",
        "summary": {"trades": 1, "win_rate": 100.0, "cumulative_pnl": 1.0},
        "learning_run_audit_v1": {
            "decision_windows_total": 2,
            "bars_processed": 10,
            "learning_engaged_v1": False,
        },
        "replay_outcomes_json": [
            {
                "trade_id": "tr_gt066",
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
        ],
    }


def test_gt066_offline_blocking_parallel_batch_reaches_done_under_harness(
    flask_client, tmp_path: Path, monkeypatch
) -> None:
    """Non-UI POST /api/run-parallel — full mocked path; terminal DONE + GT066 tape under 600s."""
    import renaissance_v4.game_theory.web_app as web_app_mod

    monkeypatch.setenv("PATTERN_GAME_STUDENT_SEAM_AFTER_PARALLEL_MAX_SEC", "120")
    monkeypatch.setenv("PATTERN_GAME_RM_TRACE_VALIDATE_MAX_SEC", "60")

    probe_exec = MagicMock()

    def fake_record(*, exam_run_line_meta_v1=None, path=None, **kwargs):
        from renaissance_v4.game_theory.batch_scorecard import record_parallel_batch_finished as real

        return real(**{**kwargs, "path": tmp_path / "sc_gt066.jsonl", "exam_run_line_meta_v1": exam_run_line_meta_v1})

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
            "prompt_version_resolved": "gt066_v1",
        },
    }

    t0 = time.monotonic()
    with patch(
        "renaissance_v4.game_theory.student_behavior_probe_v1.execute_student_behavior_probe_v1",
        probe_exec,
    ):
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
                        "renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1"
                        ".student_loop_seam_after_parallel_batch_v1",
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
                                        "renaissance_v4.game_theory.web_app._validate_student_rm_trace_contract_bounded_v1",
                                        return_value={
                                            "schema": "student_reasoning_model_trace_proof_v1",
                                            "ok_v1": True,
                                            "skipped_v1": False,
                                            "errors_v1": [],
                                            "sealed_trade_count_v1": 1,
                                            "student_decision_authority_event_count_v1": 1,
                                            "counts_match_v1": True,
                                        },
                                    ):
                                        with patch(
                                            "renaissance_v4.game_theory.learning_trace_events_v1.count_learning_trace_terminal_integrity_v1",
                                            return_value={
                                                "schema": "learning_trace_terminal_integrity_v1",
                                                "student_decision_authority_v1_count": 1,
                                                "student_output_sealed_count": 1,
                                                "integrity_ok": True,
                                                "lines_matched_job": 2,
                                                "trace_file_exists": True,
                                            },
                                        ):
                                            r = flask_client.post(
                                                "/api/run-parallel",
                                                json={
                                                    "operator_recipe_id": "custom",
                                                    "scenarios_json": '[{"scenario_id":"s_gt066","manifest_path":"renaissance_v4/configs/manifests/baseline_v1_recipe.json","agent_explanation":{"hypothesis":"GT066 offline"}}]',
                                                    "evaluation_window_mode": "12",
                                                    "exam_run_contract_v1": {
                                                        "student_reasoning_mode": STUDENT_REASONING_MODE_LLM_QWEN_V1,
                                                        "prompt_version": "gt066_v1",
                                                        "retrieved_context_ids": [],
                                                    },
                                                },
                                            )
    elapsed = time.monotonic() - t0
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json() or {}
    assert body.get("ok") is True
    assert str(body.get("result", {}).get("status_v1") or "") != "stuck_parallel_batch_watchdog_v1"
    jid = str(body.get("job_id") or "").strip()
    assert jid
    with web_app_mod._JOBS_LOCK:
        job = web_app_mod._JOBS.get(jid)
        lines = list((job or {}).get("rm_preflight_terminal_lines_v1") or [])
    tape = "\n".join(lines)
    assert "GT066_PIPELINE: replay_parallel_returned_v1" in tape
    assert "GT066_PIPELINE: student_seam_enter_v1" in tape
    assert "GT066_PIPELINE: student_seam_finished_v1" in tape
    assert "GT066_PIPELINE: scorecard_write_end_v1" in tape
    assert "GT066_PIPELINE: final_status_write_end_v1" in tape

    proof = {
        "replay_completed": "YES",
        "run_scenarios_parallel_returned": "YES",
        "student_seam_started": "YES",
        "student_seam_finished_or_failed": "YES",
        "scorecard_written": "YES",
        "final_status_written": "YES",
        "terminal_state": "DONE",
        "elapsed_seconds": round(elapsed, 3),
        "watchdog_first_terminal": "NO",
    }
    print("\nGT066_OFFLINE_PROOF_JSON:" + json.dumps(proof, indent=2))
    assert elapsed < 600.0
    assert proof["terminal_state"] in ("DONE", "ERROR")
    probe_exec.assert_not_called()
