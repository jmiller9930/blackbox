"""QEL auto-advance, full survival pass, drop, promotion_ready path."""

from __future__ import annotations

from pathlib import Path

from modules.anna_training.execution_ledger import (
    append_execution_trade,
    connect_ledger,
    ensure_execution_ledger_schema,
    sync_strategy_registry_from_catalog,
)
from modules.anna_training.quantitative_evaluation_layer.constants import (
    LIFECYCLE_CANDIDATE,
    LIFECYCLE_PROMOTION_READY,
    LIFECYCLE_TEST,
)
from modules.anna_training.quantitative_evaluation_layer.lifecycle import (
    apply_strategy_transition,
    create_survival_test,
)
from modules.anna_training.quantitative_evaluation_layer.lifecycle_advance import (
    all_enabled_checkpoints_survived,
    enabled_checkpoint_keys,
)
from modules.anna_training.quantitative_evaluation_layer.runtime import run_qel_survival_tick
from modules.anna_training.quantitative_evaluation_layer.survival_engine import run_survival_checkpoints_for_test


def _minimal_survival_config() -> dict:
    """Only trades + distinctiveness + performance — no regime/time/distinct-events gates."""
    return {
        "qel_version": "1",
        "lifecycle_auto": {"enabled": True, "min_completed_survived_for_promotion_ready": 3},
        "regime_v1": {
            "vol_low_below": 0.003,
            "vol_mid_below": 0.012,
            "flat_abs_pct": 0.0005,
        },
        "checkpoints": {
            "min_economic_trades": {"enabled": True, "min_count": 5},
            "min_distinct_market_events": {"enabled": False},
            "min_calendar_span_days": {"enabled": False},
            "distinctiveness_hash": {"enabled": True},
            "min_regime_vol_buckets": {"enabled": False},
            "min_performance": {
                "enabled": True,
                "min_total_pnl_usd": -1e9,
                "min_win_rate_decisive": 0.0,
            },
        },
    }


def _econ_trades(tmp_db: Path, sid: str, n: int, *, pnl_positive: bool = True) -> None:
    for i in range(n):
        ep, xp = (100.0, 101.0) if pnl_positive else (100.0, 99.0)
        append_execution_trade(
            strategy_id=sid,
            lane="anna",
            mode="paper",
            market_event_id=f"mev_{i}",
            symbol="SOL",
            timeframe="5m",
            side="long",
            entry_price=ep,
            exit_price=xp,
            size=1.0,
            db_path=tmp_db,
        )


def test_enabled_keys_respects_disabled() -> None:
    cfg = _minimal_survival_config()
    keys = enabled_checkpoint_keys(cfg)
    assert "min_regime_vol_buckets" not in keys
    assert "min_economic_trades" in keys


def test_survival_advances_test_to_candidate_and_tick_runs(tmp_path: Path) -> None:
    db = tmp_path / "el.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    sync_strategy_registry_from_catalog(conn)
    conn.close()

    sid = "jupiter_supertrend_ema_rsi_atr_v1"
    hyp = {"suite": "lifecycle_test", "v": 1}
    t1 = create_survival_test(
        strategy_id=sid,
        hypothesis=hyp,
        allowed_inputs={},
        lanes=["anna"],
        modes=["paper"],
        db_path=db,
    )["test_id"]

    apply_strategy_transition(
        strategy_id=sid,
        to_state=LIFECYCLE_TEST,
        reason_code="pytest",
        actor="system",
        db_path=db,
    )

    _econ_trades(db, sid, 5)

    cfg = _minimal_survival_config()
    r = run_survival_checkpoints_for_test(t1, db_path=db, config=cfg)
    assert r["ok"] is True
    assert r.get("stopped_at_drop") is False
    assert r.get("lifecycle_advance", {}).get("advanced") is True
    from modules.anna_training.quantitative_evaluation_layer.lifecycle import get_strategy_lifecycle_state

    assert get_strategy_lifecycle_state(sid, db_path=db) == LIFECYCLE_CANDIDATE

    tick = run_qel_survival_tick(db_path=db, config=_minimal_survival_config())
    assert tick["ok"] is True
    assert tick["tests_evaluated"] >= 1


def test_drop_sets_completed_dropped(tmp_path: Path) -> None:
    db = tmp_path / "el2.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    sync_strategy_registry_from_catalog(conn)
    conn.close()

    sid = "manual_operator_v1"
    t1 = create_survival_test(
        strategy_id=sid,
        hypothesis={"x": "drop_me"},
        allowed_inputs={},
        lanes=["anna"],
        modes=["paper"],
        db_path=db,
    )["test_id"]
    apply_strategy_transition(
        strategy_id=sid,
        to_state=LIFECYCLE_TEST,
        reason_code="pytest",
        actor="system",
        db_path=db,
    )
    _econ_trades(db, sid, 5, pnl_positive=False)
    cfg = _minimal_survival_config()
    cfg["checkpoints"]["min_performance"] = {
        "enabled": True,
        "min_total_pnl_usd": 1e9,
        "min_win_rate_decisive": 0.99,
    }
    r = run_survival_checkpoints_for_test(t1, db_path=db, config=cfg)
    assert r["stopped_at_drop"] is True
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    row = conn.execute(
        "SELECT status FROM anna_survival_tests WHERE test_id = ?", (t1,)
    ).fetchone()
    conn.close()
    assert row and str(row[0]) == "completed_dropped"


def _active_test_id(db: Path, sid: str) -> str:
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    cur = conn.execute(
        "SELECT test_id FROM anna_survival_tests WHERE strategy_id = ? AND status = 'active' LIMIT 1",
        (sid,),
    )
    row = cur.fetchone()
    conn.close()
    assert row
    return str(row[0])


def test_three_survival_passes_reach_promotion_ready(tmp_path: Path) -> None:
    db = tmp_path / "el3.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    sync_strategy_registry_from_catalog(conn)
    conn.close()

    sid = "jupiter_supertrend_ema_rsi_atr_v1"
    cfg = _minimal_survival_config()

    t1 = create_survival_test(
        strategy_id=sid,
        hypothesis={"round": 0},
        allowed_inputs={},
        lanes=["anna"],
        modes=["paper"],
        db_path=db,
    )["test_id"]
    apply_strategy_transition(
        strategy_id=sid,
        to_state=LIFECYCLE_TEST,
        reason_code="pytest_reset",
        actor="system",
        db_path=db,
    )
    _econ_trades(db, sid, 5)
    r1 = run_survival_checkpoints_for_test(t1, db_path=db, config=cfg)
    assert r1["ok"] is True
    assert r1.get("lifecycle_advance", {}).get("advanced") is True

    t2 = _active_test_id(db, sid)
    _econ_trades(db, sid, 5)
    r2 = run_survival_checkpoints_for_test(t2, db_path=db, config=cfg)
    assert r2.get("lifecycle_advance", {}).get("advanced") is True

    t3 = _active_test_id(db, sid)
    _econ_trades(db, sid, 5)
    r3 = run_survival_checkpoints_for_test(t3, db_path=db, config=cfg)
    assert r3.get("lifecycle_advance", {}).get("advanced") is True

    from modules.anna_training.quantitative_evaluation_layer.lifecycle import get_strategy_lifecycle_state

    assert get_strategy_lifecycle_state(sid, db_path=db) == LIFECYCLE_PROMOTION_READY


def test_remain_in_test_until_full_pass(tmp_path: Path) -> None:
    db = tmp_path / "el4.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    sync_strategy_registry_from_catalog(conn)
    conn.close()

    sid = "jupiter_supertrend_ema_rsi_atr_v1"
    tid = create_survival_test(
        strategy_id=sid,
        hypothesis={"partial": True},
        allowed_inputs={},
        lanes=["anna"],
        modes=["paper"],
        db_path=db,
    )["test_id"]
    apply_strategy_transition(
        strategy_id=sid,
        to_state=LIFECYCLE_TEST,
        reason_code="pytest",
        actor="system",
        db_path=db,
    )
    _econ_trades(db, sid, 3)
    cfg = _minimal_survival_config()
    r = run_survival_checkpoints_for_test(tid, db_path=db, config=cfg)
    assert r["ok"] is True
    assert r.get("lifecycle_advance") is None
    from modules.anna_training.quantitative_evaluation_layer.lifecycle import get_strategy_lifecycle_state

    assert get_strategy_lifecycle_state(sid, db_path=db) == LIFECYCLE_TEST

    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    ok = all_enabled_checkpoints_survived(conn, tid, cfg)
    conn.close()
    assert ok is False
