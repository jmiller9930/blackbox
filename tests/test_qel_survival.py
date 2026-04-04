"""Quantitative Evaluation Layer — survival, lifecycle, ledger authority."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.anna_training.execution_ledger import (
    append_execution_trade,
    connect_ledger,
    ensure_execution_ledger_schema,
    sync_strategy_registry_from_catalog,
)
from modules.anna_training.quantitative_evaluation_layer.constants import LIFECYCLE_TEST
from modules.anna_training.quantitative_evaluation_layer.hypothesis_hash import normalized_hypothesis_hash
from modules.anna_training.quantitative_evaluation_layer.lifecycle import (
    apply_strategy_transition,
    create_survival_test,
    validate_experiment_to_test_prerequisites,
)
from modules.anna_training.quantitative_evaluation_layer.regime_tags_v1 import VOL_HIGH, VOL_LOW, regime_tags_v1_from_bar
from modules.anna_training.quantitative_evaluation_layer.survival_engine import run_survival_checkpoints_for_test


def test_normalized_hypothesis_hash_stable() -> None:
    a = normalized_hypothesis_hash({"b": 2, "a": 1})
    b = normalized_hypothesis_hash({"a": 1, "b": 2})
    assert a == b
    assert len(a) == 64


def test_regime_tags_v1_buckets() -> None:
    low = regime_tags_v1_from_bar(
        {"open": 100.0, "high": 100.2, "low": 99.9, "close": 100.0},
        vol_low_below=0.003,
        vol_mid_below=0.012,
    )
    assert low.get("vol_bucket") == VOL_LOW
    hi = regime_tags_v1_from_bar(
        {"open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0},
        vol_low_below=0.003,
        vol_mid_below=0.012,
    )
    assert hi.get("vol_bucket") == VOL_HIGH


def test_experiment_to_test_requires_survival_test(tmp_path: Path) -> None:
    db = tmp_path / "el.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    sync_strategy_registry_from_catalog(conn)
    conn.close()

    ok, errs = validate_experiment_to_test_prerequisites("jupiter_supertrend_ema_rsi_atr_v1", db_path=db)
    assert ok is False
    assert "no_active_survival_test" in errs


def _base_config() -> dict:
    return {
        "qel_version": "1",
        "regime_v1": {
            "vol_low_below": 0.003,
            "vol_mid_below": 0.012,
            "flat_abs_pct": 0.0005,
        },
        "checkpoints": {
            "min_economic_trades": {"enabled": True, "min_count": 5},
            "min_distinct_market_events": {"enabled": True, "min_count": 5},
            "min_calendar_span_days": {"enabled": True, "min_days": 1},
            "distinctiveness_hash": {"enabled": True},
            "min_regime_vol_buckets": {"enabled": False},
            "min_performance": {
                "enabled": True,
                "min_total_pnl_usd": -1e9,
                "min_win_rate_decisive": 0.0,
            },
        },
    }


def test_survival_flow_experiment_to_test_and_checkpoints(tmp_path: Path) -> None:
    db = tmp_path / "el.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    sync_strategy_registry_from_catalog(conn)
    conn.close()

    sid = "jupiter_supertrend_ema_rsi_atr_v1"
    hyp = {"suite": "pytest_qel", "v": 1}
    out = create_survival_test(
        strategy_id=sid,
        hypothesis=hyp,
        allowed_inputs={"symbols": ["SOL-USD"]},
        lanes=["anna"],
        modes=["paper"],
        created_by="pytest",
        db_path=db,
    )
    test_id = out["test_id"]

    ok, errs = validate_experiment_to_test_prerequisites(sid, db_path=db)
    assert ok is True, errs

    tr = apply_strategy_transition(
        strategy_id=sid,
        to_state=LIFECYCLE_TEST,
        reason_code="qel_experiment_ready",
        actor="system",
        db_path=db,
    )
    assert tr["to_state"] == LIFECYCLE_TEST

    for i in range(5):
        append_execution_trade(
            strategy_id=sid,
            lane="anna",
            mode="paper",
            market_event_id=f"mev_{i}",
            symbol="SOL",
            timeframe="5m",
            side="long",
            entry_price=100.0,
            exit_price=101.0,
            size=1.0,
            db_path=db,
        )

    res = run_survival_checkpoints_for_test(test_id, db_path=db, config=_base_config())
    assert res["ok"] is True
    names = [r.get("checkpoint_name") for r in res["runs"]]
    assert "min_economic_trades" in names
    assert "min_distinct_market_events" in names
    assert "distinctiveness_hash" in names
    assert res["stopped_at_drop"] is False


def test_distinctiveness_drops_duplicate_hypothesis_across_tests(tmp_path: Path) -> None:
    db = tmp_path / "el.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    sync_strategy_registry_from_catalog(conn)
    conn.close()

    hyp = {"shared": "dup_hash"}
    t1 = create_survival_test(
        strategy_id="jupiter_supertrend_ema_rsi_atr_v1",
        hypothesis=hyp,
        allowed_inputs={},
        lanes=["anna"],
        modes=["paper"],
        db_path=db,
    )["test_id"]
    t2 = create_survival_test(
        strategy_id="manual_operator_v1",
        hypothesis=hyp,
        allowed_inputs={},
        lanes=["anna"],
        modes=["paper"],
        db_path=db,
    )["test_id"]

    for i in range(5):
        append_execution_trade(
            strategy_id="manual_operator_v1",
            lane="anna",
            mode="paper",
            market_event_id=f"m2_{i}",
            symbol="SOL",
            timeframe="5m",
            side="long",
            entry_price=100.0,
            exit_price=99.0,
            size=1.0,
            db_path=db,
        )

    res = run_survival_checkpoints_for_test(t2, db_path=db, config=_base_config())
    assert res["ok"] is True
    drop = [r for r in res["runs"] if r.get("checkpoint_name") == "distinctiveness_hash"]
    assert any(r.get("decision") == "drop" for r in drop)
    assert res["stopped_at_drop"] is True
