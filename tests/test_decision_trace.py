"""Decision trace persistence and API-shaped reads."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.anna_training.decision_trace import (
    persist_baseline_trade_with_trace,
    persist_parallel_anna_stub_trade_with_trace,
    query_trace_by_trade_id,
    query_traces_by_market_event_id,
    query_traces_by_strategy_id,
)
from modules.anna_training.execution_ledger import connect_ledger, ensure_execution_ledger_schema


def _bar() -> dict:
    return {
        "id": 42,
        "canonical_symbol": "SOL-PERP",
        "timeframe": "5m",
        "candle_open_utc": "2026-04-01T19:55:00Z",
        "candle_close_utc": "2026-04-01T20:00:00Z",
        "market_event_id": "SOL-PERP_5m_2026-04-01T19:55:00Z",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
    }


def test_parallel_anna_stub_trace_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "el.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(db))
    bar = _bar()
    out = persist_parallel_anna_stub_trade_with_trace(
        market_event_id=bar["market_event_id"],
        strategy_id="s_test_parallel_v1",
        bar=bar,
        stub_result="won",
        stub_pnl_usd=1.23,
        trade_id="trade_parallel_test_1",
        context_snapshot={"synthetic": True, "stub_pnl_usd": 1.23},
        notes="test",
        db_path=db,
    )
    assert out["trace_id"]
    assert out["execution_trade"]["trace_id"] == out["trace_id"]
    assert out["execution_trade"]["trade_id"] == "trade_parallel_test_1"

    tr = query_trace_by_trade_id("trade_parallel_test_1", db_path=db)
    assert tr is not None
    assert tr["trace_id"] == out["trace_id"]
    assert tr["lane"] == "anna"
    assert tr["paper_stub"] is True
    assert len(tr["steps"]) == 5
    assert tr["steps"][0]["step_name"] == "ingest"
    assert tr["steps"][-1]["step_name"] == "execution"

    by_mid = query_traces_by_market_event_id(bar["market_event_id"], db_path=db)
    assert len(by_mid) == 1
    by_sid = query_traces_by_strategy_id("s_test_parallel_v1", db_path=db)
    assert len(by_sid) == 1

    conn = connect_ledger(db)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            "SELECT trace_id FROM execution_trades WHERE trade_id = ?",
            ("trade_parallel_test_1",),
        )
        row = cur.fetchone()
        assert row and row[0] == out["trace_id"]
    finally:
        conn.close()


def test_baseline_trace_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "el.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(db))
    bar = _bar()
    out = persist_baseline_trade_with_trace(
        market_event_id=bar["market_event_id"],
        bar=bar,
        mode="paper",
        trade_id="trade_baseline_test_1",
        pnl_usd=0.5,
        context_snapshot={"source": "test"},
        notes="test",
        db_path=db,
    )
    assert out["trace_id"]
    assert out["execution_trade"]["trace_id"] == out["trace_id"]
    tr = query_trace_by_trade_id("trade_baseline_test_1", db_path=db)
    assert tr is not None
    assert tr["lane"] == "baseline"
    assert tr["paper_stub"] is False
