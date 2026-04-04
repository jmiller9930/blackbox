"""Evaluation summary API (QEL judgment view)."""

from __future__ import annotations

from pathlib import Path

from modules.anna_training.evaluation_summary import build_evaluation_summary
from modules.anna_training.execution_ledger import (
    append_execution_trade,
    connect_ledger,
    ensure_execution_ledger_schema,
    sync_strategy_registry_from_catalog,
)
from modules.anna_training.quantitative_evaluation_layer.lifecycle import create_survival_test


def test_evaluation_summary_requires_strategy_id() -> None:
    out = build_evaluation_summary({})
    assert out["ok"] is False
    assert "strategy_id" in (out.get("error") or "")


def test_evaluation_summary_smoke(tmp_path: Path) -> None:
    db = tmp_path / "el.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    sync_strategy_registry_from_catalog(conn)
    conn.close()

    sid = "jupiter_supertrend_ema_rsi_atr_v1"
    create_survival_test(
        strategy_id=sid,
        hypothesis={"v": 1},
        allowed_inputs={},
        lanes=["anna"],
        modes=["paper"],
        db_path=db,
    )
    for i in range(3):
        append_execution_trade(
            strategy_id=sid,
            lane="anna",
            mode="paper",
            market_event_id=f"ev_{i}",
            symbol="SOL",
            timeframe="5m",
            side="long",
            entry_price=100.0,
            exit_price=101.0,
            size=1.0,
            db_path=db,
        )

    out = build_evaluation_summary({"strategy_id": [sid]}, db_path=db)
    assert out["ok"] is True
    assert out["schema"] == "anna_evaluation_summary_v1"
    assert out["lifecycle"]["lifecycle_state"] == "experiment"
    assert isinstance(out["checkpoints"], list)
    assert "strategy_cohort" in out["metrics"]
    assert out["metrics"]["strategy_cohort"]["trade_count"] == 3
    ce = out.get("canonical_evaluation") or {}
    assert ce.get("schema") == "canonical_evaluation_v1"
    assert "readiness_state" in ce
    assert "checkpoints" in ce
