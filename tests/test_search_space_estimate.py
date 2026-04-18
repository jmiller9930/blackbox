"""Finite search-space estimate for catalog + bars + parallel hints."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory.search_space_estimate import build_search_space_estimate

_REPO = Path(__file__).resolve().parents[1]


def test_estimate_has_catalog_and_combinatorics() -> None:
    j = build_search_space_estimate()
    assert j["catalog"]["signals_count"] == 4
    assert j["combinatorics"]["non_empty_signal_subsets_upper_bound"] == 15


def test_parallel_rounds_ceil() -> None:
    j = build_search_space_estimate(batch_size=10, workers=4)
    assert j["workload_hints"]["parallel_rounds_ceil_batch_over_workers"] == 3


def test_bar_replay_units_when_batch_and_bars_known(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "renaissance_v4.game_theory.search_space_estimate.count_market_bars",
        lambda: (1000, None),
    )
    j = build_search_space_estimate(batch_size=5, workers=2)
    assert j["bar_replay_units"] == 5000


def test_web_api_search_space_estimate() -> None:
    from renaissance_v4.game_theory.web_app import create_app

    app = create_app()
    c = app.test_client()
    r = c.get("/api/search-space-estimate?batch_size=8&workers=4")
    assert r.status_code == 200
    j = r.get_json()
    assert j["catalog"]["signals_count"] == 4
    assert j["workload_hints"]["parallel_rounds_ceil_batch_over_workers"] == 2
