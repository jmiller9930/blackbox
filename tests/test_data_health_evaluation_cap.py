"""Max evaluation window vs replay tape span (DB-derived cap)."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.data_health import max_evaluation_window_calendar_months_from_span_days
from renaissance_v4.game_theory.web_app import _prepare_parallel_payload


def test_max_months_from_span_ceil() -> None:
    assert max_evaluation_window_calendar_months_from_span_days(None) is None
    assert max_evaluation_window_calendar_months_from_span_days(0) is None
    assert max_evaluation_window_calendar_months_from_span_days(20) == 1
    assert max_evaluation_window_calendar_months_from_span_days(365) == 12
    m5y = max_evaluation_window_calendar_months_from_span_days(5 * 365.25)
    assert 58 <= m5y <= 62


def test_prepare_parallel_rejects_window_over_tape_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_health() -> dict:
        return {
            "max_evaluation_window_calendar_months": 10,
            "replay_tape_span_days_approx": 300.0,
            "all_bars_span_days": 300.0,
        }

    monkeypatch.setattr("renaissance_v4.game_theory.web_app.get_data_health", fake_health)
    prep = _prepare_parallel_payload(
        {
            "operator_recipe_id": "pattern_learning",
            "evaluation_window_mode": "24",
            "evaluation_window_custom_months": None,
            "scenarios_json": "[]",
        }
    )
    assert prep.get("ok") is False
    assert "exceeds" in str(prep.get("error", "")).lower()
    assert prep.get("max_evaluation_window_calendar_months") == 10


def test_prepare_parallel_allows_window_under_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "renaissance_v4.game_theory.web_app.get_data_health",
        lambda: {"max_evaluation_window_calendar_months": 100, "replay_tape_span_days_approx": 4000.0},
    )
    prep = _prepare_parallel_payload(
        {
            "operator_recipe_id": "pattern_learning",
            "evaluation_window_mode": "12",
            "evaluation_window_custom_months": None,
            "scenarios_json": "[]",
        }
    )
    assert prep.get("ok") is True
