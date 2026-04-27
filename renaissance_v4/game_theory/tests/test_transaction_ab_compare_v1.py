"""Transaction-level Baseline vs Student compare (replay outcomes, no operator-facing data_gap strings)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from renaissance_v4.game_theory.transaction_ab_compare_v1 import (
    build_transaction_ab_compare_v1,
    transaction_ab_compare_to_csv_v1,
)


def _trade(**kw) -> dict:
    base = {
        "trade_id": "t1",
        "symbol": "X",
        "direction": "long",
        "entry_time": 1_000_000,
        "exit_time": 1_900_000,
        "entry_price": 100.0,
        "exit_price": 101.0,
        "exit_reason": "target",
        "pnl": 1.5,
        "metadata": {"bars_in_trade": 3},
    }
    base.update(kw)
    return base


def _payload(scenario_id: str, outcomes: list[dict]) -> dict:
    return {
        "schema": "batch_parallel_results_v1",
        "scenario_order": [scenario_id],
        "results": [
            {
                "ok": True,
                "scenario_id": scenario_id,
                "replay_outcomes_json": outcomes,
            }
        ],
    }


def _fake_decision_rec(**over) -> dict:
    r = {
        "schema": "student_decision_record_v1",
        "ok": True,
        "influence_summary": "student_learning_record_v1:rec-026c-abc",
        "retrieval_count": 1,
        "student_confidence_01": 0.72,
        "student_action_v1": "enter_long",
    }
    r.update(over)
    return r


@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.read_learning_trace_events_for_job_v1")
@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.build_student_decision_record_v1")
@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.load_batch_parallel_results_v1")
@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.build_scenario_list_for_batch")
@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.find_scorecard_entry_by_job_id")
def test_transaction_ab_pair_and_csv_no_data_gap_string(
    mock_find, mock_build_list, mock_load, mock_d14, mock_trace, tmp_path: Path
):
    (tmp_path / "job_a").mkdir(parents=True)
    (tmp_path / "job_b").mkdir(parents=True)
    tmp = tmp_path
    mock_trace.return_value = [
        {
            "stage": "reasoning_router_decision_v1",
            "evidence_payload": {
                "reasoning_router_decision_v1": {
                    "final_route_v1": "local_only",
                    "escalation_decision_v1": "no_escalation",
                    "escalation_reason_codes_v1": [],
                    "external_api_attempted_v1": False,
                }
            },
        }
    ]

    def _find(jid: str):
        return {
            "job_id": jid,
            "session_log_batch_dir": str(tmp / jid),
            "operator_batch_audit": {"candle_timeframe_minutes": 5},
            "student_retrieval_matches": 1,
        }

    mock_find.side_effect = _find

    def _build(jid: str, bd: str | None):
        return (Path(bd or "").resolve(), [{"scenario_id": "s1", "folder": "f1"}], None)

    mock_build_list.side_effect = _build

    oj_a = _trade(trade_id="ta1", direction="long", pnl=1.0)
    oj_b = _trade(trade_id="tb1", direction="short", pnl=-0.5, exit_reason="stop")
    mock_load.side_effect = lambda batch_dir: (
        _payload("s1", [oj_a]) if Path(batch_dir).name == "job_a" else _payload("s1", [oj_b])
    )

    mock_d14.return_value = _fake_decision_rec()

    out = build_transaction_ab_compare_v1(
        job_id_baseline="job_a",
        job_id_student="job_b",
        scenario_id="s1",
    )
    assert out.get("ok") is True
    assert out.get("schema") == "operator_transaction_ab_compare_v1"
    rows = out.get("rows") or []
    assert len(rows) == 1
    assert rows[0]["delta"]["decision_changed"] is True
    assert rows[0]["delta"]["pnl_delta"] == -1.5
    lo = rows[0]["learning_overlay_b_v1"]
    assert lo.get("learning_record_id") == "rec-026c-abc"
    assert lo.get("learning_retrieved") is True
    assert out["router_overlay_job_b_v1"].get("router_invoked") is True

    csv_text = transaction_ab_compare_to_csv_v1(out)
    assert "data_gap" not in csv_text.lower()


@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.read_learning_trace_events_for_job_v1", return_value=[])
@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.build_student_decision_record_v1", return_value=None)
@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.load_batch_parallel_results_v1")
@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.build_scenario_list_for_batch")
@patch("renaissance_v4.game_theory.transaction_ab_compare_v1.find_scorecard_entry_by_job_id")
def test_transaction_ab_mismatched_trade_counts(mock_find, mock_build_list, mock_load, _mock_d14, _mock_tr, tmp_path: Path):
    (tmp_path / "job_a").mkdir(parents=True)
    (tmp_path / "job_b").mkdir(parents=True)
    tmp = tmp_path

    def _find(jid: str):
        return {
            "job_id": jid,
            "session_log_batch_dir": str(tmp / jid),
            "operator_batch_audit": {"candle_timeframe_minutes": 5},
        }

    mock_find.side_effect = _find
    mock_build_list.side_effect = lambda jid, bd: (Path(bd or "").resolve(), [{"scenario_id": "s1", "folder": "f1"}], None)
    mock_load.side_effect = lambda batch_dir: (
        _payload("s1", [_trade(trade_id="a1"), _trade(trade_id="a2", entry_time=2_000_000)])
        if Path(batch_dir).name == "job_a"
        else _payload("s1", [_trade(trade_id="b1", direction="short")])
    )

    out = build_transaction_ab_compare_v1(
        job_id_baseline="job_a",
        job_id_student="job_b",
        scenario_id="s1",
    )
    assert out.get("ok") is True
    rows = out["rows"]
    assert len(rows) == 2
    assert rows[1]["baseline"] is not None
    assert rows[1]["student"] is None
    assert rows[1]["delta"]["decision_changed"] is True
