"""Parallel runner: economic paper default; stub requires lab opt-in; stub migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.anna_training.parallel_strategy_runner import (
    _migrate_anna_parallel_stub_rows_to_paper,
    _parallel_strategy_mode,
    run_parallel_anna_strategies_tick,
)
from modules.anna_training.sean_jupiter_baseline_signal import SeanJupiterBaselineSignalV1


def test_parallel_mode_defaults_to_paper_when_stub_without_lab(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_PARALLEL_STRATEGY_MODE", "paper_stub")
    monkeypatch.delenv("ANNA_PARALLEL_STUB_LAB", raising=False)
    assert _parallel_strategy_mode() == "paper"


def test_parallel_mode_stub_when_lab_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_PARALLEL_STRATEGY_MODE", "paper_stub")
    monkeypatch.setenv("ANNA_PARALLEL_STUB_LAB", "1")
    assert _parallel_strategy_mode() == "paper_stub"


def test_parallel_runner_no_trade_when_signal_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sean Jupiter returns trade=False → no Anna execution rows (signal-gated)."""
    import sqlite3

    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(tmp_path / "e.db"))
    mp = tmp_path / "m.db"
    conn_m = sqlite3.connect(str(mp))
    conn_m.executescript(
        """
        CREATE TABLE market_bars_5m (
          id INTEGER PRIMARY KEY,
          canonical_symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL,
          candle_open_utc TEXT,
          candle_close_utc TEXT,
          market_event_id TEXT NOT NULL,
          open REAL, high REAL, low REAL, close REAL,
          tick_count INTEGER, price_source TEXT, computed_at TEXT
        );
        INSERT INTO market_bars_5m (
          canonical_symbol, timeframe, candle_open_utc, candle_close_utc, market_event_id,
          open, high, low, close, tick_count, price_source, computed_at
        ) VALUES (
          'SOL-PERP', '5m', '2026-04-01T00:00:00Z', '2026-04-01T00:05:00Z', 'SOL-PERP_5m_2026-04-01T00:00:00Z',
          100.0, 101.0, 99.0, 100.5, 1, 't', '2026-04-01T00:05:01Z'
        );
        """
    )
    conn_m.commit()
    conn_m.close()
    monkeypatch.setenv("BLACKBOX_MARKET_DATA_PATH", str(mp))

    monkeypatch.setattr(
        "modules.anna_training.parallel_strategy_runner.evaluate_sean_jupiter_baseline_v1",
        lambda bars_asc, **_kw: SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="no_signal",
            pnl_usd=None,
            features={},
        ),
    )

    out = run_parallel_anna_strategies_tick(
        market_data_db_path=mp,
        execution_ledger_db_path=tmp_path / "e.db",
    )
    assert out.get("ok") is True
    assert out.get("no_trade") is True
    assert out.get("reason_code") == "no_signal"
    assert out.get("trades_written") == 0


def test_migrate_stub_row_gets_pnl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy paper_stub row + market bar → upgraded to paper + pnl_usd."""
    monkeypatch.setenv("BLACKBOX_MARKET_DATA_PATH", str(tmp_path / "m.db"))
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(tmp_path / "e.db"))

    import sqlite3

    from modules.anna_training.execution_ledger import connect_ledger, ensure_execution_ledger_schema

    mp = tmp_path / "m.db"
    conn_m = sqlite3.connect(str(mp))
    conn_m.executescript(
        """
        CREATE TABLE market_bars_5m (
          id INTEGER PRIMARY KEY,
          canonical_symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL,
          candle_open_utc TEXT,
          candle_close_utc TEXT,
          market_event_id TEXT NOT NULL,
          open REAL, high REAL, low REAL, close REAL,
          tick_count INTEGER, price_source TEXT, computed_at TEXT
        );
        INSERT INTO market_bars_5m (
          canonical_symbol, timeframe, candle_open_utc, candle_close_utc, market_event_id,
          open, high, low, close, tick_count, price_source, computed_at
        ) VALUES (
          'SOL-PERP', '5m', '2026-04-01T00:00:00Z', '2026-04-01T00:05:00Z', 'e_test_1',
          100.0, 101.0, 99.0, 100.5, 1, 't', '2026-04-01T00:05:01Z'
        );
        """
    )
    conn_m.commit()
    conn_m.close()

    el = tmp_path / "e.db"
    conn = connect_ledger(el)
    ensure_execution_ledger_schema(conn)
    conn.execute(
        """
        INSERT INTO execution_trades (
          trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
          side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
          pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
        ) VALUES (
          'pt_test1', 'jupiter_2_sean_perps_v1', 'anna', 'paper_stub', 'e_test_1',
          'SOL-PERP', '5m', 'long', '2026-04-01T00:00:00Z', 100.0, 1.0,
          '2026-04-01T00:05:00Z', 100.0, 'CLOSE',
          NULL, '{}', 'parallel_stub synthetic (pnl_usd not asserted)', NULL,
          'execution_trade_v1', '2026-04-01T00:05:00Z'
        )
        """
    )
    conn.commit()

    out = _migrate_anna_parallel_stub_rows_to_paper(conn, market_db_path=mp)
    conn.close()
    assert out.get("updated") == 1

    conn2 = connect_ledger(el)
    cur = conn2.execute(
        "SELECT mode, pnl_usd FROM execution_trades WHERE trade_id = 'pt_test1'"
    )
    row = cur.fetchone()
    conn2.close()
    assert row is not None
    assert row[0] == "paper"
    assert row[1] is not None and abs(float(row[1]) - 0.5) < 1e-6
