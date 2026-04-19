"""Tests for bundle_optimizer v1 (deterministic rules, no LLM)."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.bundle_optimizer import (
    BundleOptimizerError,
    extract_metrics_from_pattern_game_run,
    optimize_bundle_v1,
)


def test_extract_requires_summary_sanity() -> None:
    with pytest.raises(BundleOptimizerError):
        extract_metrics_from_pattern_game_run({})


def test_optimize_no_trades_relax_fusion() -> None:
    m = {
        "source_run_id": "abc",
        "total_trades": 0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "cumulative_pnl": 0.0,
        "fusion_no_trade_bars": 50,
        "fusion_directional_bars": 5,
        "entries_attempted": 0,
        "closes_recorded": 0,
        "risk_blocked_bars": 0,
        "dataset_bars": 100,
        "scorecards": {},
    }
    bundle, proof = optimize_bundle_v1(
        m,
        manifest_signal_modules=["mean_reversion_fade", "trend_continuation"],
    )
    assert "fusion_min_score" in bundle["apply"]
    assert proof["no_changes"] is False
    assert "V1_NO_TRADES_RELAX_FUSION" in proof["reason_codes"]


def test_optimize_no_changes_when_rules_not_met() -> None:
    m = {
        "source_run_id": "x",
        "total_trades": 0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "cumulative_pnl": 0.0,
        "fusion_no_trade_bars": 3,
        "fusion_directional_bars": 1,
        "entries_attempted": 0,
        "closes_recorded": 0,
        "risk_blocked_bars": 0,
        "dataset_bars": 10,
        "scorecards": {},
    }
    bundle, proof = optimize_bundle_v1(m, manifest_signal_modules=["mean_reversion_fade"])
    assert bundle["apply"] == {}
    assert proof["no_changes"] is True
    assert "no_changes_reason" in proof


def test_optimize_high_dd_tightens() -> None:
    m = {
        "source_run_id": "y",
        "total_trades": 3,
        "max_drawdown": 50.0,
        "win_rate": 0.4,
        "expectancy": -1.0,
        "cumulative_pnl": -10.0,
        "fusion_no_trade_bars": 10,
        "fusion_directional_bars": 40,
        "entries_attempted": 5,
        "closes_recorded": 3,
        "risk_blocked_bars": 0,
        "dataset_bars": 100,
        "scorecards": {},
    }
    bundle, proof = optimize_bundle_v1(m, manifest_signal_modules=["mean_reversion_fade"])
    assert "fusion_min_score" in bundle["apply"] or "atr_stop_mult" in bundle["apply"]
    assert proof["no_changes"] is False
