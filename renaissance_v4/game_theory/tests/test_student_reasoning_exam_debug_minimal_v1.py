"""GT060 — minimal debug exam returns exactly one scenario at 5m."""

from pathlib import Path

from renaissance_v4.game_theory.exam.student_reasoning_exam_scenarios_v1 import (
    DEBUG_MINIMAL_EXAM_IDS_V1,
    resolve_scenario_windows_v1,
)
from renaissance_v4.utils.db import DB_PATH


def test_debug_exam_id_registered() -> None:
    assert "d15-debug-001" in DEBUG_MINIMAL_EXAM_IDS_V1


def test_resolve_debug_returns_one_scenario_five_minute() -> None:
    rows, err = resolve_scenario_windows_v1(db_path=DB_PATH, exam_id="d15-debug-001")
    assert err is None, err
    assert len(rows) == 1
    assert int(rows[0]["candle_timeframe_minutes"]) == 5
