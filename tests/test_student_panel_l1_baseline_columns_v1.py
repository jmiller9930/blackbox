"""L1 run row — system baseline vs this-run trade win % (student_panel_run_row_v2)."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.student_panel_d11 import build_d11_run_rows_v1


def _row(
    job_id: str,
    *,
    tw: float,
    fp: str = "testfp0123456789012345678901234567890ab",
    status: str = "done",
) -> dict:
    return {
        "job_id": job_id,
        "status": status,
        "started_at_utc": "2026-04-20T12:00:00Z",
        "batch_trade_win_pct": tw,
        "batch_trades_count": 100,
        "expectancy_per_trade": 0.02,
        "student_output_fingerprint": "x",
        "scenario_id": "scen_a",
        "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
        "memory_context_impact_audit_v1": {
            "run_config_fingerprint_sha256_40": fp,
        },
    }


def test_l1_anchor_row_beats_column_is_dash() -> None:
    rows = build_d11_run_rows_v1([_row("only1", tw=34.5)])
    assert len(rows) == 1
    r = rows[0]
    assert r["harness_baseline_trade_win_percent"] == 34.5
    assert r["run_trade_win_percent"] == 34.5
    assert r["beats_system_baseline_trade_win"] == "—"


def test_l1_second_run_strictly_beats_anchor() -> None:
    # Newest-first merge order: pass [newer, older] so anchor is older (34.5), newer is 40
    rows = build_d11_run_rows_v1([_row("job_new", tw=40.0), _row("job_old", tw=34.5)])
    by_id = {str(x["run_id"]): x for x in rows}
    assert by_id["job_new"]["beats_system_baseline_trade_win"] == "YES"
    assert by_id["job_new"]["harness_baseline_trade_win_percent"] == 34.5
    assert by_id["job_new"]["run_trade_win_percent"] == 40.0
    assert by_id["job_old"]["beats_system_baseline_trade_win"] == "—"
    assert by_id["job_old"]["run_trade_win_percent"] == 34.5


def test_l1_second_run_strictly_below_anchor() -> None:
    rows = build_d11_run_rows_v1([_row("job_new", tw=30.0), _row("job_old", tw=34.5)])
    by_id = {str(x["run_id"]): x for x in rows}
    assert by_id["job_new"]["beats_system_baseline_trade_win"] == "NO"


def test_l1_tie_with_anchor_shows_equals() -> None:
    rows = build_d11_run_rows_v1([_row("job_new", tw=34.5), _row("job_old", tw=34.5)])
    by_id = {str(x["run_id"]): x for x in rows}
    assert by_id["job_new"]["beats_system_baseline_trade_win"] == "="


def test_l1_operator_time_requires_end_for_duration() -> None:
    rows = build_d11_run_rows_v1([_row("j1", tw=40.0)])
    r = rows[0]
    assert r["l1_utc_primary_source_v1"] == "started_at_utc"
    assert r["l1_job_duration_seconds_v1"] is None
    assert r["l1_job_duration_gap_v1"] == "missing_ended_at_utc"


def test_l1_operator_time_wall_clock_duration() -> None:
    line = _row("j2", tw=40.0)
    line["ended_at_utc"] = "2026-04-20T12:22:14Z"
    line["duration_sec"] = 999.0
    rows = build_d11_run_rows_v1([line])
    r = rows[0]
    assert r["l1_utc_primary_source_v1"] == "ended_at_utc"
    assert r["l1_utc_primary_iso_v1"] == "2026-04-20T12:22:14Z"
    assert r["l1_job_duration_basis_v1"] == "wall_clock_started_at_ended_at_utc"
    assert r["l1_job_duration_seconds_v1"] == pytest.approx(1334.0)
    assert r["l1_job_duration_gap_v1"] is None
