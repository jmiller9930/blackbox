"""Operator Baseline vs Student Markdown report (A/B proof artifact)."""

from __future__ import annotations

from unittest.mock import patch

from renaissance_v4.game_theory import operator_ab_report_v1 as m


def _fake_trace_b() -> dict:
    return {
        "ok": True,
        "learning_trace_events_v1": [],
        "lifecycle_trace_overlay_v1": {
            "lifecycle_tape_summary_v1": {"exit_reason_code_v1": "test_exit"}
        },
        "learning_effect_closure_026c_v1": {
            "closure_result_v1": "INSUFFICIENT_COMPARISON",
            "closure_detail_v1": "control_job_id not supplied",
            "run_b_026c_injection_and_apply_v1": {},
        },
        "breakpoints_v1": ("bp1",),
        "student_reasoning_fault_map_v1": None,
    }


def _fake_trace_a() -> dict:
    return {
        "ok": True,
        "learning_trace_events_v1": [],
        "lifecycle_trace_overlay_v1": {},
    }


@patch("renaissance_v4.game_theory.scorecard_drill.find_scorecard_entry_by_job_id")
@patch("renaissance_v4.game_theory.debug_learning_loop_trace_v1.build_debug_learning_loop_trace_v1")
@patch(
    "renaissance_v4.game_theory.reasoning_model_operator_surface_v1"
    ".get_reasoning_model_operator_snapshot_v1",
)
def test_report_markdown_has_required_sections(mock_snap, mock_debug, mock_find):
    mock_find.return_value = {
        "student_action_v1": "enter_long",
        "avg_trade_win_pct": 0.5,
        "expectancy_per_trade": 0.1,
        "operator_batch_audit": {
            "operator_recipe_id": "test_recipe",
            "evaluation_window_mode": "12",
            "trade_window_mode": "5m",
        },
    }

    def _dbg(jid, **kw):
        if jid == "job_a":
            return _fake_trace_a()
        return _fake_trace_b()

    mock_debug.side_effect = _dbg
    mock_snap.return_value = {
        "primary_escalation_code_v1": "ok",
        "escalation_summary_v1": "—",
        "headline_badge_v1": "Idle",
        "fields_v1": {"headline_badge_v1": "Idle", "external_api_health": "available"},
    }

    out = m.build_operator_baseline_vs_student_report_markdown_v1(
        job_id_baseline="job_a",
        job_id_student="job_b",
        environment="test-host",
        ui_version="9.9.9",
    )
    for heading in (
        "## 1. Run identification",
        "## 2. High-level outcome",
        "## 3. Decision comparison",
        "## 4. Reasoning summary",
        "## 5. Router behavior",
        "## 6. Lifecycle outcome",
        "## 7. Learning (026C)",
        "## 8. System health",
        "## 9. Operator conclusion",
    ):
        assert heading in out, heading
    assert "job_a" in out and "job_b" in out
    assert "9.9.9" in out
    assert "test-host" in out


@patch("renaissance_v4.game_theory.scorecard_drill.find_scorecard_entry_by_job_id", return_value=None)
@patch(
    "renaissance_v4.game_theory.debug_learning_loop_trace_v1.build_debug_learning_loop_trace_v1",
    return_value={"ok": False, "learning_trace_events_v1": []},
)
@patch(
    "renaissance_v4.game_theory.reasoning_model_operator_surface_v1"
    ".get_reasoning_model_operator_snapshot_v1",
    return_value={},
)
def test_report_runs_with_empty_scorecard(mock_snap, mock_debug, mock_find):
    out = m.build_operator_baseline_vs_student_report_markdown_v1(
        job_id_baseline="na",
        job_id_student="nb",
    )
    assert "Baseline vs Student" in out
    assert "na" in out
