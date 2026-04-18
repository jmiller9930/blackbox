"""Tests for pattern-game outcome scoring and manifest ATR validation."""

from __future__ import annotations

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.manifest.validate import validate_manifest_against_catalog
from renaissance_v4.game_theory.pattern_game import (
    OUTCOME_RULE_V1,
    score_binary_outcomes,
)


def test_score_binary_outcomes_win_loss_breakeven() -> None:
    o = [
        OutcomeRecord(
            trade_id="a",
            symbol="SOLUSDT",
            direction="long",
            entry_time=1,
            exit_time=2,
            entry_price=100.0,
            exit_price=101.0,
            pnl=1.0,
            mae=0.0,
            mfe=1.0,
            exit_reason="target",
        ),
        OutcomeRecord(
            trade_id="b",
            symbol="SOLUSDT",
            direction="long",
            entry_time=3,
            exit_time=4,
            entry_price=100.0,
            exit_price=99.0,
            pnl=-1.0,
            mae=1.0,
            mfe=0.0,
            exit_reason="stop",
        ),
        OutcomeRecord(
            trade_id="c",
            symbol="SOLUSDT",
            direction="long",
            entry_time=5,
            exit_time=6,
            entry_price=100.0,
            exit_price=100.0,
            pnl=0.0,
            mae=0.0,
            mfe=0.0,
            exit_reason="target",
        ),
    ]
    s = score_binary_outcomes(o)
    assert s["outcome_rule_version"] == OUTCOME_RULE_V1
    assert s["wins"] == 1
    assert s["losses"] == 2
    assert s["trades"] == 3
    assert abs(s["win_rate"] - (1.0 / 3.0)) < 1e-9


def test_validate_manifest_atr_bounds() -> None:
    base = {
        "schema": "strategy_manifest_v1",
        "manifest_version": "1.0",
        "strategy_id": "test",
        "strategy_name": "test",
        "baseline_tag": "t",
        "timeframe": "5m",
        "factor_pipeline": "feature_set_v1",
        "signal_modules": ["trend_continuation"],
        "regime_module": "regime_v1_default",
        "risk_model": "risk_governor_v1_default",
        "fusion_module": "fusion_geometric_v1",
        "execution_template": "execution_manager_v1_default",
        "experiment_type": "replay_full_history",
        "atr_stop_mult": 10.0,
    }
    errs = validate_manifest_against_catalog(base)
    assert any("atr_stop_mult" in e for e in errs)

    base["atr_stop_mult"] = 2.0
    base["atr_target_mult"] = 3.0
    errs2 = validate_manifest_against_catalog(base)
    assert errs2 == []


def test_execution_manager_atr_constructor() -> None:
    from renaissance_v4.core.execution_manager import ATR_STOP_MULT, ATR_TARGET_MULT, ExecutionManager

    em = ExecutionManager()
    assert em.atr_stop_mult == ATR_STOP_MULT
    assert em.atr_target_mult == ATR_TARGET_MULT

    em2 = ExecutionManager(atr_stop_mult=1.0, atr_target_mult=2.0)
    assert em2.atr_stop_mult == 1.0
    assert em2.atr_target_mult == 2.0
