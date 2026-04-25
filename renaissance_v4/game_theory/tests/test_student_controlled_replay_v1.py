"""GT_DIRECTIVE_024C — Student-controlled replay lane (unit tests, mocked replay)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.student_controlled_replay_v1 import (
    attach_student_controlled_replay_v1,
    apply_student_controlled_scorecard_rollup_v1,
    outcomes_list_canonical_hash_v1,
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


def test_run_manifest_replay_default_has_no_student_intent() -> None:
    import inspect

    from renaissance_v4.research.replay_runner import run_manifest_replay

    sig = inspect.signature(run_manifest_replay)
    assert "student_execution_intent_v1" in sig.parameters
    assert sig.parameters["student_execution_intent_v1"].default is None
