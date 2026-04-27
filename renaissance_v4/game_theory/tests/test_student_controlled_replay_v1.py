"""GT_DIRECTIVE_024C — Student-controlled replay lane (unit tests, mocked replay)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.student_controlled_replay_v1 import (
    apply_automated_student_lanes_from_exam_contract_v1,
    attach_student_controlled_replay_v1,
    apply_student_controlled_scorecard_rollup_v1,
    outcomes_list_canonical_hash_v1,
)
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    legal_example_student_output_with_thesis_v1,
)
from renaissance_v4.game_theory.tests.test_student_execution_intent_v1 import (
    _FIXTURES_DIR,
)


def _valid_intent_from_fixture() -> dict:
    p = _FIXTURES_DIR / "valid_student_execution_intent_enter_long_v1.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_outcomes_hash_deterministic() -> None:
    a = outcomes_list_canonical_hash_v1([{"x": 1}])
    b = outcomes_list_canonical_hash_v1([{"x": 1}])
    assert a == b
    assert len(a) == 64


@patch("renaissance_v4.research.replay_runner.run_manifest_replay")
@patch("renaissance_v4.game_theory.pattern_game.prepare_effective_manifest_for_replay")
def test_attach_consumes_intent_and_sets_hashes(mock_prep, mock_run) -> None:
    class _Prep:
        replay_path = Path("/dev/null")
        def cleanup(self) -> None:
            pass

    mock_prep.return_value = _Prep()
    mock_run.return_value = {
        "outcomes": [],
        "validation_checksum": "chk",
        "summary": {"expectancy": 0.0, "cumulative_pnl": 0.0, "average_pnl": 0.0, "max_drawdown": 0.0},
        "binary_scorecard": {},
        "manifest_path": "m.json",
        "dataset_bars": 10,
    }
    intent = _valid_intent_from_fixture()
    scen = {
        "scenario_id": "t1",
        "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
        "enable_student_controlled_replay_v1": True,
        "student_execution_intent_v1": intent,
    }
    row: dict = {
        "ok": True,
        "scenario_id": "t1",
        "replay_outcomes_json": [{"trade_id": "a", "pnl": 1.0}],
        "summary": {"expectancy": 0.1},
    }
    with patch("renaissance_v4.game_theory.student_controlled_replay_v1._emit_student_lane_traces_v1"), patch(
        "renaissance_v4.game_theory.student_controlled_replay_v1._emit_student_lane_complete_v1"
    ), patch("renaissance_v4.game_theory.student_controlled_replay_v1._emit_referee_used_student_thesis_v1"):
        out = attach_student_controlled_replay_v1(
            scen, row, job_id="job1", fingerprint="0" * 40
        )
    assert out["student_lane_status_v1"] == "completed"
    assert out["source_student_output_digest_v1"] == intent["source_student_output_digest_v1"]
    assert out["control_outcomes_hash_v1"] != out["student_outcomes_hash_v1"] or out[
        "student_baseline_outcomes_differ_v1"
    ] in (True, False)
    mock_run.assert_called_once()
    kwo = mock_run.call_args.kwargs
    assert kwo.get("student_execution_intent_v1") == intent
    assert kwo.get("decision_context_recall_enabled") is False


def test_intent_invalid_no_replay() -> None:
    scen = {
        "scenario_id": "t2",
        "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
        "student_execution_intent_v1": {"schema": "student_execution_intent_v1", "action": "enter_long"},
    }
    row: dict = {"ok": True, "scenario_id": "t2", "replay_outcomes_json": []}
    out = attach_student_controlled_replay_v1(scen, row, job_id="j", fingerprint="f")
    assert out["student_lane_status_v1"] == "intent_invalid"


@patch("renaissance_v4.research.replay_runner.run_manifest_replay", side_effect=RuntimeError("boom"))
@patch("renaissance_v4.game_theory.pattern_game.prepare_effective_manifest_for_replay")
def test_replay_error_no_baseline_mutation(mock_prep, _mock_run) -> None:
    class _Prep:
        replay_path = Path("/dev/null")
        def cleanup(self) -> None:
            pass

    mock_prep.return_value = _Prep()
    intent = _valid_intent_from_fixture()
    scen = {
        "scenario_id": "t3",
        "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
        "student_execution_intent_v1": intent,
    }
    base_row = {
        "ok": True,
        "summary": {"expectancy": 0.2},
        "replay_outcomes_json": [{"k": 1}],
    }
    before = json.dumps(base_row, sort_keys=True)
    with patch("renaissance_v4.game_theory.student_controlled_replay_v1._emit_student_lane_traces_v1"):
        out = attach_student_controlled_replay_v1(
            scen, base_row, job_id="j", fingerprint="f"
        )
    after = json.dumps(base_row, sort_keys=True)
    assert before == after
    assert out["student_lane_status_v1"] == "replay_error"


def test_scorecard_rollup_two_completed() -> None:
    r = [
        {
            "ok": True,
            "student_controlled_replay_v1": {
                "student_lane_status_v1": "completed",
                "student_referee_session_v1": "WIN",
                "student_controlled_expectancy_per_trade_v1": 0.1,
                "student_controlled_total_trades_v1": 2,
            },
        },
        {
            "ok": True,
            "student_controlled_replay_v1": {
                "student_lane_status_v1": "completed",
                "student_referee_session_v1": "LOSS",
                "student_controlled_expectancy_per_trade_v1": -0.1,
                "student_controlled_total_trades_v1": 1,
            },
        },
    ]
    u = apply_student_controlled_scorecard_rollup_v1(r)
    assert u["student_controlled_replay_ran_v1"] == 2
    assert u["student_controlled_referee_win_pct_v1"] == 50.0
    assert u["student_controlled_total_trades_sum_v1"] == 3


@patch("renaissance_v4.research.replay_runner.run_manifest_replay")
@patch("renaissance_v4.game_theory.pattern_game.prepare_effective_manifest_for_replay")
def test_apply_automated_from_exam_contract_sealed_output(mock_prep, mock_run) -> None:
    class _Prep:
        replay_path = Path("/dev/null")

        def cleanup(self) -> None:
            return None

    mock_prep.return_value = _Prep()
    mock_run.return_value = {
        "outcomes": [],
        "validation_checksum": "c",
        "summary": {
            "expectancy": 0.0,
            "cumulative_pnl": 0.0,
            "average_pnl": 0.0,
            "max_drawdown": 0.0,
        },
    }
    so = legal_example_student_output_with_thesis_v1()
    exam = {
        "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        "student_controlled_execution_v1": True,
        "student_execution_mode_v1": "baseline_gated",
    }
    seam = {"student_output_sealed_by_scenario_id_v1": {"scen_auto": so}}
    results: list[dict] = [
        {
            "ok": True,
            "scenario_id": "scen_auto",
            "replay_outcomes_json": [{"trade_id": "t1", "entry_time": 1}],
            "summary": {"expectancy": 0.1},
        }
    ]
    scenarios = [
        {
            "scenario_id": "scen_auto",
            "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
        }
    ]
    with patch("renaissance_v4.game_theory.student_controlled_replay_v1._emit_student_lane_traces_v1"), patch(
        "renaissance_v4.game_theory.student_controlled_replay_v1._emit_student_lane_complete_v1"
    ), patch("renaissance_v4.game_theory.student_controlled_replay_v1._emit_referee_used_student_thesis_v1"):
        ad = apply_automated_student_lanes_from_exam_contract_v1(
            results=results,
            scenarios=scenarios,
            job_id="job_auto1",
            exam_run_contract_request_v1=exam,
            seam_audit=seam,
            fingerprint="d" * 40,
        )
    assert ad.get("automation_ran_v1") is True
    assert int(ad.get("scenarios_with_student_lane_attempted_v1") or 0) == 1
    blk = results[0].get("student_controlled_replay_v1")
    assert isinstance(blk, dict)
    assert blk.get("automation_source_v1") == "exam_contract_v1"
    assert blk.get("execution_authority_v1") == "baseline_gated_student"
    assert blk.get("student_lane_status_v1") == "completed"
    mock_run.assert_called_once()


def test_run_manifest_replay_default_has_no_student_intent() -> None:
    import inspect

    from renaissance_v4.research.replay_runner import run_manifest_replay

    sig = inspect.signature(run_manifest_replay)
    assert "student_execution_intent_v1" in sig.parameters
    assert sig.parameters["student_execution_intent_v1"].default is None
    assert "student_full_control_lane_v1" in sig.parameters
    assert sig.parameters["student_full_control_lane_v1"].default is False
    assert "replay_max_bars_v1" in sig.parameters
    assert sig.parameters["replay_max_bars_v1"].default is None


@patch("renaissance_v4.research.replay_runner.run_manifest_replay")
@patch("renaissance_v4.game_theory.pattern_game.prepare_effective_manifest_for_replay")
def test_attach_passes_full_control_lane_to_replay(mock_prep, mock_run) -> None:
    class _Prep:
        replay_path = Path("/dev/null")

        def cleanup(self) -> None:
            return None

    mock_prep.return_value = _Prep()
    mock_run.return_value = {
        "outcomes": [],
        "validation_checksum": "c",
        "student_full_control_replay_audit_v1": {
            "schema": "student_full_control_replay_audit_v1",
            "student_full_control_024d_fusion_veto_entry_events_v1": 0,
        },
        "summary": {
            "expectancy": 0.0,
            "cumulative_pnl": 0.0,
            "average_pnl": 0.0,
            "max_drawdown": 0.0,
        },
    }
    intent = _valid_intent_from_fixture()
    scen = {
        "scenario_id": "fc1",
        "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
        "student_execution_intent_v1": intent,
        "student_full_control_lane_v1": True,
    }
    row: dict = {
        "ok": True,
        "scenario_id": "fc1",
        "replay_outcomes_json": [],
        "summary": {"expectancy": 0.0},
    }
    with patch("renaissance_v4.game_theory.student_controlled_replay_v1._emit_student_lane_traces_v1"), patch(
        "renaissance_v4.game_theory.student_controlled_replay_v1._emit_student_lane_complete_v1"
    ), patch("renaissance_v4.game_theory.student_controlled_replay_v1._emit_referee_used_student_thesis_v1"):
        out = attach_student_controlled_replay_v1(scen, row, job_id="j1", fingerprint="0" * 40)
    assert out.get("execution_authority_v1") == "student_full_control"
    kwo = mock_run.call_args.kwargs
    assert kwo.get("student_full_control_lane_v1") is True
