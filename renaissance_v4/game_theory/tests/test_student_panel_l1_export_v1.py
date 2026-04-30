"""student_panel_l1_export_v1 — synthetic merged scorecard slice."""

from __future__ import annotations

from unittest.mock import patch

from renaissance_v4.game_theory.student_panel_l1_export_v1 import build_student_panel_l1_row_export_v1


def _minimal_done_line(*, job_id: str) -> dict:
    return {
        "schema": "pattern_game_batch_scorecard_v1",
        "job_id": job_id,
        "status": "done",
        "started_at_utc": "2026-01-01T00:00:00Z",
        "ended_at_utc": "2026-01-01T01:00:00Z",
        "batch_trades_count": 5,
        "batch_trade_win_pct": 55.0,
        "expectancy_per_trade": 0.0123,
        "operator_batch_audit": {
            "operator_recipe_id": "recipe_unit_test",
            "evaluation_window_effective_calendar_months": 12,
        },
    }


def test_l1_export_ok_with_merged_slice() -> None:
    jid = "l1-export-test-job"
    merged = [_minimal_done_line(job_id=jid)]
    with patch(
        "renaissance_v4.game_theory.student_panel_l1_export_v1.find_scorecard_entry_by_job_id",
        return_value=merged[0],
    ):
        out = build_student_panel_l1_row_export_v1(jid, merged_entries_newest_first=merged)
    assert out.get("ok") is True
    assert out.get("schema") == "student_panel_l1_row_export_v1"
    assert out.get("job_id") == jid
    assert isinstance(out.get("scorecard_line_v1"), dict)
    prow = out.get("student_panel_run_row_v2")
    assert isinstance(prow, dict)
    assert prow.get("run_id") == jid
    assert prow.get("schema") == "student_panel_run_row_v2"


def test_l1_export_missing_job() -> None:
    merged = [_minimal_done_line(job_id="other")]
    out = build_student_panel_l1_row_export_v1("nope", merged_entries_newest_first=merged)
    assert out.get("ok") is False
    assert out.get("error") == "run_row_not_found_v1"
