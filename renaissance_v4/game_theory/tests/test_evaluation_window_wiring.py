"""Wiring tests for operator evaluation window resolution and recipe payload merge."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.evaluation_window_runtime import (
    resolve_ui_evaluation_window,
    slice_rows_for_calendar_months,
)
from renaissance_v4.game_theory.operator_recipes import (
    build_scenarios_for_recipe,
    recipe_meta_by_id,
)
from renaissance_v4.game_theory.web_app import _prepare_parallel_payload


@pytest.fixture(autouse=True)
def _generous_tape_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real lab DB spans vary; these wiring tests assume enough tape for 12/24 mo windows."""
    monkeypatch.setattr(
        "renaissance_v4.game_theory.web_app.get_data_health",
        lambda: {
            "max_evaluation_window_calendar_months": 600,
            "replay_tape_span_days_approx": 20000.0,
        },
    )


def test_resolve_ui_window_modes() -> None:
    r12 = resolve_ui_evaluation_window("12", None)
    assert r12["effective_calendar_months"] == 12
    r24 = resolve_ui_evaluation_window("24", None)
    assert r24["effective_calendar_months"] == 24
    rc = resolve_ui_evaluation_window("custom", 30)
    assert rc["effective_calendar_months"] == 30


def test_prepare_parallel_pattern_learning_default_window() -> None:
    prep = _prepare_parallel_payload(
        {
            "operator_recipe_id": "pattern_learning",
            "evaluation_window_mode": "12",
            "evaluation_window_custom_months": None,
            "scenarios_json": "[]",
        }
    )
    assert prep["ok"] is True
    assert prep["operator_batch_audit"]["operator_recipe_id"] == "pattern_learning"
    assert prep["operator_batch_audit"]["evaluation_window_effective_calendar_months"] == 12
    assert prep["operator_batch_audit"]["trade_window_mode"] == "5m"
    assert prep["operator_batch_audit"]["candle_timeframe_minutes"] == 5
    assert prep["operator_batch_audit"]["window_overrode_recipe_default"] is False
    assert len(prep["scenarios"]) == 1
    assert prep["scenarios"][0].get("goal_v2") is not None
    ew = prep["scenarios"][0]["evaluation_window"]
    assert ew.get("candle_timeframe_minutes") == 5


def test_prepare_parallel_trade_window_1h() -> None:
    prep = _prepare_parallel_payload(
        {
            "operator_recipe_id": "pattern_learning",
            "evaluation_window_mode": "12",
            "evaluation_window_custom_months": None,
            "trade_window_mode": "1h",
            "scenarios_json": "[]",
        }
    )
    assert prep["ok"] is True
    assert prep["operator_batch_audit"]["trade_window_mode"] == "1h"
    assert prep["operator_batch_audit"]["candle_timeframe_minutes"] == 60
    assert prep["scenarios"][0]["evaluation_window"]["candle_timeframe_minutes"] == 60


def test_prepare_parallel_invalid_trade_window() -> None:
    prep = _prepare_parallel_payload(
        {
            "operator_recipe_id": "pattern_learning",
            "evaluation_window_mode": "12",
            "trade_window_mode": "30m",
            "scenarios_json": "[]",
        }
    )
    assert prep["ok"] is False
    err = str(prep.get("error") or "").lower()
    assert "trade_window" in err or "5m" in err


def test_prepare_parallel_override_24_months() -> None:
    meta = recipe_meta_by_id("pattern_learning")
    assert meta is not None
    prep = _prepare_parallel_payload(
        {
            "operator_recipe_id": "pattern_learning",
            "evaluation_window_mode": "24",
            "evaluation_window_custom_months": None,
            "scenarios_json": "[]",
        }
    )
    assert prep["ok"] is True
    assert prep["operator_batch_audit"]["evaluation_window_effective_calendar_months"] == 24
    assert prep["operator_batch_audit"]["window_overrode_recipe_default"] is True
    ew = prep["scenarios"][0]["evaluation_window"]
    assert ew["calendar_months"] == 24


def test_slice_rows_produces_shorter_list() -> None:
    rows = []
    base = 1700000000
    # ~83 days of hourly bars — a 1-calendar-month tail slice must drop the oldest segment.
    for i in range(2000):
        rows.append({"open_time": base + i * 3600, "symbol": "X"})
    sliced, audit = slice_rows_for_calendar_months(rows, calendar_months=1, min_rows_required=50)
    assert audit["slicing_applied"] is True
    assert len(sliced) < len(rows)
    assert len(sliced) >= 50


def test_build_reference_comparison_three_scenarios() -> None:
    s = build_scenarios_for_recipe("reference_comparison")
    assert len(s) == 3
