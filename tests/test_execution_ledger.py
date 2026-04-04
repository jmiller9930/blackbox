"""Execution ledger — parallel identity rows."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    append_execution_trade,
    connect_ledger,
    ensure_execution_ledger_schema,
    query_trades_by_market_event_id,
    sync_strategy_registry_from_catalog,
)


def test_lane_strategy_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(tmp_path / "el.db"))
    with pytest.raises(ValueError, match="baseline"):
        append_execution_trade(
            strategy_id="foo",
            lane="baseline",
            mode="paper",
            market_event_id="SOL-PERP_5m_2026-04-01T19:55:00Z",
            symbol="SOL-PERP",
            timeframe="5m",
        )
    with pytest.raises(ValueError, match="baseline"):
        append_execution_trade(
            strategy_id=RESERVED_STRATEGY_BASELINE,
            lane="anna",
            mode="paper",
            market_event_id="SOL-PERP_5m_2026-04-01T19:55:00Z",
            symbol="SOL-PERP",
            timeframe="5m",
        )


def test_multiple_trades_same_market_event_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(tmp_path / "el.db"))
    mid = "SOL-PERP_5m_2026-04-01T19:55:00Z"
    append_execution_trade(
        strategy_id="jupiter_supertrend_ema_rsi_atr_v1",
        lane="anna",
        mode="paper",
        market_event_id=mid,
        symbol="SOL-PERP",
        timeframe="5m",
        entry_time="2026-04-01T19:55:00Z",
        entry_price=100.0,
        exit_time="2026-04-01T20:00:00Z",
        exit_price=101.0,
        exit_reason="CLOSE",
        pnl_usd=1.0,
        trade_id="t-anna-1",
    )
    append_execution_trade(
        strategy_id="monopoly",
        lane="anna",
        mode="paper",
        market_event_id=mid,
        symbol="SOL-PERP",
        timeframe="5m",
        entry_time="2026-04-01T19:55:00Z",
        entry_price=100.0,
        exit_time="2026-04-01T20:00:00Z",
        exit_price=99.0,
        exit_reason="CLOSE",
        pnl_usd=-1.0,
        trade_id="t-anna-2",
    )
    append_execution_trade(
        strategy_id=RESERVED_STRATEGY_BASELINE,
        lane="baseline",
        mode="paper",
        market_event_id=mid,
        symbol="SOL-PERP",
        timeframe="5m",
        entry_time="2026-04-01T19:55:00Z",
        entry_price=100.0,
        exit_time="2026-04-01T20:00:00Z",
        exit_price=100.5,
        exit_reason="TP",
        pnl_usd=0.5,
        trade_id="t-base-1",
    )
    rows = query_trades_by_market_event_id(mid)
    assert len(rows) == 3
    lanes = {r["lane"] for r in rows}
    assert lanes == {"anna", "baseline"}


def test_sync_strategy_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(tmp_path / "el.db"))
    conn = connect_ledger()
    ensure_execution_ledger_schema(conn)
    n = sync_strategy_registry_from_catalog(conn)
    assert n >= 2
    cur = conn.execute("SELECT COUNT(*) FROM strategy_registry")
    assert cur.fetchone()[0] >= 2
    conn.close()
