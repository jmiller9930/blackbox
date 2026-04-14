"""Sean parity SQLite vs Blackbox binance_strategy_bars_5m + policy."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_RT = _ROOT / "scripts" / "runtime"
if str(_RT) not in sys.path:
    sys.path.insert(0, str(_RT))

from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP, TICK_SYMBOL_SOL_DEFAULT, TIMEFRAME_5M
from market_data.canonical_time import candle_close_utc_exclusive, format_candle_open_iso_z
from market_data.market_event_id import make_market_event_id
from market_data.store import connect_market_db, ensure_market_schema, upsert_binance_strategy_bar_5m
from modules.anna_training.execution_ledger import (
    SIGNAL_MODE_JUPITER_3,
    connect_ledger,
    ensure_execution_ledger_schema,
    upsert_policy_evaluation,
)
from modules.anna_training.jup_v3_parity_compare import compare_sean_sqlite_to_blackbox
from datetime import datetime, timezone


def _one_open() -> datetime:
    return datetime(2026, 4, 14, 1, 5, 0, tzinfo=timezone.utc)


def test_compare_match_close_and_policy(tmp_path: Path) -> None:
    op = _one_open()
    close_b = candle_close_utc_exclusive(op)
    meid = make_market_event_id(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=op,
        timeframe=TIMEFRAME_5M,
    )
    co = format_candle_open_iso_z(op)

    mdb = tmp_path / "market_data.db"
    conn = connect_market_db(mdb)
    ensure_market_schema(conn)
    upsert_binance_strategy_bar_5m(
        conn,
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        tick_symbol=TICK_SYMBOL_SOL_DEFAULT,
        timeframe=TIMEFRAME_5M,
        candle_open_utc=co,
        candle_close_utc=format_candle_open_iso_z(close_b),
        market_event_id=meid,
        open_px=100.0,
        high_px=101.0,
        low_px=99.0,
        close_px=100.5,
        volume_base_asset=10.0,
        quote_volume_usdt=1000.0,
    )
    conn.close()

    ldb = tmp_path / "ledger.db"
    lconn = connect_ledger(ldb)
    ensure_execution_ledger_schema(lconn)
    upsert_policy_evaluation(
        market_event_id=meid,
        signal_mode=SIGNAL_MODE_JUPITER_3,
        tick_mode="paper",
        trade=False,
        reason_code="test_idle",
        features={},
        side="flat",
        conn=lconn,
    )
    lconn.commit()
    lconn.close()

    sdb = tmp_path / "sean_parity.db"
    sconn = sqlite3.connect(sdb)
    sconn.executescript(
        """
        CREATE TABLE sean_binance_kline_poll (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          market_event_id TEXT NOT NULL,
          candle_open_ms INTEGER NOT NULL,
          open_px TEXT,
          high_px TEXT,
          low_px TEXT,
          close_px TEXT,
          volume_base TEXT,
          polled_at_utc TEXT NOT NULL,
          url TEXT,
          latency_ms INTEGER
        );
        """
    )
    sconn.execute(
        """
        INSERT INTO sean_binance_kline_poll (
          market_event_id, candle_open_ms, open_px, high_px, low_px, close_px, volume_base,
          polled_at_utc, url, latency_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (meid, int(op.timestamp() * 1000), "100", "101", "99", "100.5", "10", "2026-04-14T01:10:00Z", "http://test", 50),
    )
    sconn.commit()
    sconn.close()

    out = compare_sean_sqlite_to_blackbox(
        sean_sqlite_path=sdb,
        market_db_path=mdb,
        ledger_db_path=ldb,
    )
    assert out["ok"] is True
    assert out["summary"]["sean_rows"] == 1
    assert out["summary"]["ohlc_match"] == 1
    assert out["summary"]["policy_present"] == 1
    assert out["rows"][0]["ohlc_status"] == "match"


def test_compare_empty_sean_db(tmp_path: Path) -> None:
    sdb = tmp_path / "empty.db"
    sqlite3.connect(sdb).close()
    out = compare_sean_sqlite_to_blackbox(sean_sqlite_path=sdb, market_db_path=None)
    assert "No rows" in (out.get("plain_english") or "")
