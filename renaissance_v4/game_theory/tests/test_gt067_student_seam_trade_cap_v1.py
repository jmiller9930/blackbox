"""
GT067 — Bounded Student seam: process only first N closed replay trades (default cap 25).

Proof harness (non-UI): direct seam + optional Flask parallel path with mocked replay.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.exam_run_contract_v1 import STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1
from renaissance_v4.game_theory.learning_trace_events_v1 import (
    default_learning_trace_events_jsonl,
    read_learning_trace_events_for_job_v1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
    student_seam_max_trades_cap_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db
from renaissance_v4.game_theory.web_app import create_app


def _l3_ok(
    jid: str,
    tid: str,
    *,
    provisional_student_learning_record_v1: dict | None = None,
    **_kw: object,
) -> dict:
    return {
        "ok": True,
        "data_gaps": [],
        "decision_record_v1": {"ok": True},
        "job_id": jid,
        "trade_id": tid,
    }


def _eight_outcomes() -> list[dict]:
    rows = []
    for i in range(8):
        o = OutcomeRecord(
            trade_id=f"gt067_cap_{i}",
            symbol="TESTUSDT",
            direction="long",
            entry_time=6_000_000 + i * 10_000,
            exit_time=6_100_000 + i * 10_000,
            entry_price=100.0,
            exit_price=101.0,
            pnl=1.0,
            mae=0.0,
            mfe=0.5,
            exit_reason="tp",
        )
        rows.append(outcome_record_to_jsonable(o))
    return rows


def test_gt067_student_seam_cap_defaults_to_25(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATTERN_GAME_STUDENT_SEAM_MAX_TRADES", raising=False)
    assert student_seam_max_trades_cap_v1() == 25


def test_gt067_seam_processes_only_cap_trades_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_SEAM_MAX_TRADES", "3")
    monkeypatch.setenv("PATTERN_GAME_MEMORY_ROOT", str(tmp_path))
    db = tmp_path / "bars.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "learn.jsonl"

    t0 = time.monotonic()
    with patch(
        "renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1"
        ".build_student_panel_l3_payload_v1",
        _l3_ok,
    ):
        audit = student_loop_seam_after_parallel_batch_v1(
            results=[
                {
                    "ok": True,
                    "scenario_id": "s_gt067",
                    "replay_outcomes_json": _eight_outcomes(),
                }
            ],
            run_id="job_gt067_direct",
            db_path=db,
            store_path=store,
            strategy_id="pattern_learning",
            exam_run_contract_request_v1={
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                "prompt_version": "gt067_cap_v1",
            },
        )
    elapsed = time.monotonic() - t0

    assert audit.get("replay_closed_trades_total_v1") == 8
    assert audit.get("student_seam_max_trades_v1") == 3
    assert audit.get("student_seam_trades_skipped_due_to_cap_v1") == 5
    assert int(audit.get("trades_considered") or 0) == 3
    assert audit.get("student_seam_stop_reason_v1") == "completed_bounded_seam_trades_v1"

    trace_path = default_learning_trace_events_jsonl()
    evs = read_learning_trace_events_for_job_v1("job_gt067_direct", path=trace_path)
    auth_n = sum(1 for e in evs if e.get("stage") == "student_decision_authority_v1")
    sealed_n = sum(1 for e in evs if e.get("stage") == "student_output_sealed")

    proof = {
        "closed_trades": 8,
        "student_seam_trades_requested": 8,
        "student_seam_trades_processed": int(audit.get("trades_considered") or 0),
        "student_seam_trades_skipped_due_to_cap": int(audit.get("student_seam_trades_skipped_due_to_cap_v1") or 0),
        "student_decision_authority_v1": auth_n,
        "student_output_sealed": sealed_n,
        "terminal_state": "SEAM_OK",
        "elapsed_seconds": round(elapsed, 3),
    }
    print("\nGT067_SEAM_DIRECT_PROOF_JSON:" + json.dumps(proof, indent=2))

    assert auth_n >= 3
    assert sealed_n >= 3
    assert elapsed < 600.0


def test_gt067_offline_parallel_blocking_stub_profile_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/run-parallel — mocked parallel row with 8 trades; stub Student profile; cap 3."""
    import renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 as spr_mod

    monkeypatch.setenv("PATTERN_GAME_STUDENT_SEAM_MAX_TRADES", "3")
    monkeypatch.setenv("PATTERN_GAME_MEMORY_ROOT", str(tmp_path))
    monkeypatch.setattr(spr_mod, "DB_PATH", tmp_path / "renaissance_v4.sqlite3")
    db = tmp_path / "renaissance_v4.sqlite3"
    _mk_synthetic_db(db)

    app = create_app()
    app.config["TESTING"] = True

    scenarios_json = json.dumps(
        [
            {
                "scenario_id": "s_gt067_http",
                "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
                "agent_explanation": {"hypothesis": "GT067 cap harness"},
            }
        ]
    )

    fake_parallel = [
        {
            "ok": True,
            "scenario_id": "s_gt067_http",
            "referee_session": "WIN",
            "summary": {"trades": 8, "win_rate": 100.0, "cumulative_pnl": 8.0},
            "learning_run_audit_v1": {
                "decision_windows_total": 2,
                "bars_processed": 10,
                "learning_engaged_v1": False,
            },
            "replay_outcomes_json": _eight_outcomes(),
        }
    ]

    def fake_record(*, exam_run_line_meta_v1=None, path=None, **kwargs):
        from renaissance_v4.game_theory.batch_scorecard import record_parallel_batch_finished as real

        return real(**{**kwargs, "path": tmp_path / "sc_gt067.jsonl", "exam_run_line_meta_v1": exam_run_line_meta_v1})

    t0 = time.monotonic()
    with patch.object(spr_mod, "build_student_panel_l3_payload_v1", _l3_ok):
        import renaissance_v4.game_theory.web_app as web_app_mod

        with patch.object(web_app_mod, "record_parallel_batch_finished", side_effect=fake_record):
            with patch(
                "renaissance_v4.game_theory.rm_preflight_wiring_v1.run_rm_preflight_wiring_v1",
                return_value={
                    "schema": "rm_preflight_wiring_audit_v1",
                    "ok_v1": True,
                    "skipped_v1": True,
                    "status_v1": "skipped_rm_preflight_v1",
                    "missing_stages_v1": [],
                    "memory_sink_event_count_v1": 0,
                },
            ):
                with patch(
                    "renaissance_v4.game_theory.web_app.run_scenarios_parallel",
                    return_value=fake_parallel,
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
                                        "skipped_v1": True,
                                        "errors_v1": [],
                                    },
                                ):
                                    with app.test_client() as c:
                                        r = c.post(
                                            "/api/run-parallel",
                                            json={
                                                "operator_recipe_id": "custom",
                                                "scenarios_json": scenarios_json,
                                                "evaluation_window_mode": "12",
                                                "exam_run_contract_v1": {
                                                    "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                                                    "prompt_version": "gt067_http_v1",
                                                    "retrieved_context_ids": [],
                                                },
                                            },
                                        )
    elapsed = time.monotonic() - t0

    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json() or {}
    assert body.get("ok") is True
    err_txt = json.dumps(body)
    assert "student_seam_wall_timeout_v1" not in err_txt

    seam = body.get("student_loop_directive_09_v1") or {}
    jid = str(body.get("job_id") or "").strip()
    trace_path = default_learning_trace_events_jsonl()
    evs = read_learning_trace_events_for_job_v1(jid, path=trace_path)
    auth_n = sum(1 for e in evs if e.get("stage") == "student_decision_authority_v1")
    sealed_n = sum(1 for e in evs if e.get("stage") == "student_output_sealed")

    proof = {
        "closed_trades": int(seam.get("replay_closed_trades_total_v1") or 0),
        "student_seam_trades_requested": int(seam.get("replay_closed_trades_total_v1") or 0),
        "student_seam_trades_processed": int(seam.get("trades_considered") or 0),
        "student_seam_trades_skipped_due_to_cap": int(seam.get("student_seam_trades_skipped_due_to_cap_v1") or 0),
        "student_decision_authority_v1": auth_n,
        "student_output_sealed": sealed_n,
        "terminal_state": "DONE",
        "elapsed_seconds": round(elapsed, 3),
    }
    print("\nGT067_OFFLINE_PARALLEL_PROOF_JSON:" + json.dumps(proof, indent=2))

    assert proof["terminal_state"] == "DONE"
    assert proof["student_decision_authority_v1"] > 0
    assert proof["student_output_sealed"] > 0
    assert proof["elapsed_seconds"] < 600.0
    assert proof["student_seam_trades_skipped_due_to_cap"] == 5
    assert proof["student_seam_trades_processed"] == 3
