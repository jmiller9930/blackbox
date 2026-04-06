"""CSV export of execution_trades — entry/exit blocks."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest


def test_export_execution_trades_csv_roundtrip(tmp_path: Path) -> None:
    from modules.anna_training.execution_ledger import append_execution_trade, ensure_execution_ledger_schema
    from modules.anna_training.execution_ledger import connect_ledger
    from modules.anna_training.trade_export_csv import export_execution_trades_to_csv

    db = tmp_path / "execution_ledger.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    conn.close()

    append_execution_trade(
        trade_id="t_csv_1",
        strategy_id="baseline",
        lane="baseline",
        mode="paper",
        market_event_id="SOL-PERP_5m_2026-01-01T00:00:00Z",
        symbol="SOL-PERP",
        timeframe="5m",
        side="long",
        entry_time="2026-01-01T00:00:00Z",
        entry_price=100.0,
        size=1.0,
        exit_time="2026-01-01T00:05:00Z",
        exit_price=101.0,
        exit_reason="CLOSE",
        notes="test row",
        db_path=db,
    )

    outp = tmp_path / "out.csv"
    r = export_execution_trades_to_csv(out_path=outp, db_path=db, with_mae=False)
    assert r["ok"] is True
    assert r["rows_written"] == 1
    assert outp.is_file()

    with outp.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    row = rows[0]
    assert row["datetime_utc"] == "2026-01-01T00:00:00Z"
    assert "entry_time=2026-01-01T00:00:00Z" in row["entry"]
    assert "exit_price=101.0" in row["exit"]
    assert row["trade_id"] == "t_csv_1"
    assert row["pnl_usd"]  # derived


def test_export_empty_ledger(tmp_path: Path) -> None:
    from modules.anna_training.execution_ledger import ensure_execution_ledger_schema
    from modules.anna_training.execution_ledger import connect_ledger
    from modules.anna_training.trade_export_csv import export_execution_trades_to_csv

    db = tmp_path / "empty.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    conn.close()

    outp = tmp_path / "empty.csv"
    r = export_execution_trades_to_csv(out_path=outp, db_path=db)
    assert r["rows_written"] == 0
    with outp.open(encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) >= 1  # header only


def test_format_wl_from_pnl_and_tui_columns() -> None:
    from modules.anna_training.trade_export_csv import (
        TRADE_EXPORT_FIELDNAMES,
        TUI_WIN_LOSS_FIELD,
        format_wl_from_pnl,
        tui_ledger_column_order,
    )

    assert format_wl_from_pnl(1.5) == "W"
    assert format_wl_from_pnl(-0.01) == "L"
    assert format_wl_from_pnl(0.0) == "flat"
    assert format_wl_from_pnl(None) == "—"

    order = tui_ledger_column_order()
    assert order[0] == "datetime_utc"
    assert order[1] == TUI_WIN_LOSS_FIELD
    assert len(order) == len(TRADE_EXPORT_FIELDNAMES) + 1
    assert order[2:] == TRADE_EXPORT_FIELDNAMES[1:]

