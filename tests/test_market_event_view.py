"""Market event aggregate API — schema and baseline slot."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.anna_training.decision_trace import persist_parallel_anna_stub_trade_with_trace
from modules.anna_training.execution_ledger import RESERVED_STRATEGY_BASELINE, append_execution_trade
from modules.anna_training.market_event_view import build_market_event_view


def test_market_event_view_requires_id_when_auto_disabled() -> None:
    r = build_market_event_view({"no_auto_default": ["1"]})
    assert r.get("ok") is False
    assert r.get("error") == "missing_market_event_id"


def test_market_event_view_baseline_and_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "el.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(db))
    mid = "SOL-PERP_5m_2026-04-01T19:55:00Z"
    bar = {
        "id": 1,
        "canonical_symbol": "SOL-PERP",
        "timeframe": "5m",
        "candle_open_utc": "2026-04-01T19:55:00Z",
        "candle_close_utc": "2026-04-01T20:00:00Z",
        "market_event_id": mid,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
    }
    persist_parallel_anna_stub_trade_with_trace(
        market_event_id=mid,
        strategy_id="jupiter_supertrend_ema_rsi_atr_v1",
        bar=bar,
        stub_result="won",
        stub_pnl_usd=0.5,
        trade_id="t_ann_1",
        context_snapshot={"synthetic": True},
        notes="t",
        db_path=db,
    )
    append_execution_trade(
        trade_id="t_base_1",
        strategy_id=RESERVED_STRATEGY_BASELINE,
        lane="baseline",
        mode="paper",
        market_event_id=mid,
        symbol="SOL-PERP",
        timeframe="5m",
        side="long",
        entry_time=bar["candle_open_utc"],
        entry_price=100.0,
        size=1.0,
        exit_time=bar["candle_close_utc"],
        exit_price=100.5,
        exit_reason="CLOSE",
        db_path=db,
    )

    mdb = tmp_path / "market.db"
    monkeypatch.setenv("BLACKBOX_MARKET_DATA_PATH", str(mdb))
    import sqlite3

    conn = sqlite3.connect(mdb)
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS market_bars_5m (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          canonical_symbol TEXT NOT NULL,
          tick_symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL DEFAULT '5m',
          candle_open_utc TEXT NOT NULL,
          candle_close_utc TEXT NOT NULL,
          market_event_id TEXT NOT NULL UNIQUE,
          open REAL, high REAL, low REAL, close REAL,
          tick_count INTEGER NOT NULL DEFAULT 0,
          volume_base REAL,
          price_source TEXT NOT NULL DEFAULT 'pyth_primary',
          bar_schema_version TEXT NOT NULL DEFAULT 'canonical_bar_v1',
          computed_at TEXT NOT NULL
        );
        INSERT INTO market_bars_5m (
          canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
          market_event_id, open, high, low, close, tick_count, computed_at
        ) VALUES (
          'SOL-PERP', 'SOL-USD', '5m', '2026-04-01T19:55:00Z', '2026-04-01T20:00:00Z',
          '{mid}', 100, 101, 99, 100.5, 3, '2026-04-01T20:00:01Z'
        );
        """
    )
    conn.commit()
    conn.close()

    r = build_market_event_view({"market_event_id": [mid]})
    assert r.get("ok") is True, r
    assert r.get("schema") == "anna_market_event_view_v1"
    assert r["baseline_slot"]["state"] == "trade_recorded"
    assert len(r["trades"]) == 2
    assert len(r["decision_traces"]) >= 1
    assert any(m.get("kind") == "entry" for m in r["chart"]["markers"])
    assert r.get("trend_context", {}).get("schema") == "trend_context_v1"
    assert isinstance(r["trend_context"].get("trade_trend_alignments"), list)
