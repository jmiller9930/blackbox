"""PnL derivation, paper_stub, and ledger scan."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    append_execution_trade,
    compute_pnl_usd,
    connect_ledger,
    ensure_execution_ledger_schema,
    is_economic_mode,
    scan_execution_ledger_pnl_integrity,
)


def test_compute_pnl_long_short() -> None:
    assert compute_pnl_usd(entry_price=100.0, exit_price=101.0, size=1.0, side="long") == 1.0
    assert compute_pnl_usd(entry_price=100.0, exit_price=99.0, size=1.0, side="long") == -1.0
    assert compute_pnl_usd(entry_price=100.0, exit_price=99.0, size=1.0, side="short") == 1.0


def test_append_rejects_pnl_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(tmp_path / "el.db"))
    with pytest.raises(ValueError, match="pnl_usd mismatch"):
        append_execution_trade(
            strategy_id="jupiter_supertrend_ema_rsi_atr_v1",
            lane="anna",
            mode="paper",
            market_event_id="SOL-PERP_5m_2026-04-01T19:55:00Z",
            symbol="SOL-PERP",
            timeframe="5m",
            side="long",
            size=1.0,
            entry_time="2026-04-01T19:55:00Z",
            entry_price=100.0,
            exit_time="2026-04-01T20:00:00Z",
            exit_price=101.0,
            exit_reason="CLOSE",
            pnl_usd=99.0,
            trade_id="bad-pnl",
        )


def test_paper_stub_no_pnl_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(tmp_path / "el.db"))
    row = append_execution_trade(
        strategy_id="jupiter_supertrend_ema_rsi_atr_v1",
        lane="anna",
        mode="paper_stub",
        market_event_id="SOL-PERP_5m_2026-04-01T19:55:00Z",
        symbol="SOL-PERP",
        timeframe="5m",
        side="long",
        size=1.0,
        entry_time="2026-04-01T19:55:00Z",
        entry_price=100.0,
        exit_time="2026-04-01T20:00:00Z",
        exit_price=100.0,
        exit_reason="CLOSE",
        context_snapshot={"synthetic": True, "stub_pnl_usd": 1.23},
        trade_id="stub-1",
    )
    assert row["pnl_usd"] is None


def test_scan_clean_economic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(tmp_path / "el.db"))
    append_execution_trade(
        strategy_id=RESERVED_STRATEGY_BASELINE,
        lane="baseline",
        mode="paper",
        market_event_id="SOL-PERP_5m_2026-04-01T19:55:00Z",
        symbol="SOL-PERP",
        timeframe="5m",
        side="long",
        size=1.0,
        entry_time="2026-04-01T19:55:00Z",
        entry_price=100.0,
        exit_time="2026-04-01T20:00:00Z",
        exit_price=100.5,
        exit_reason="CLOSE",
        trade_id="b1",
    )
    out = scan_execution_ledger_pnl_integrity(db_path=tmp_path / "el.db")
    assert out["violation_count"] == 0
    assert out["economic_ok_count"] >= 1


def test_scan_flags_bad_pnl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "el.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(db))
    append_execution_trade(
        strategy_id=RESERVED_STRATEGY_BASELINE,
        lane="baseline",
        mode="paper",
        market_event_id="SOL-PERP_5m_2026-04-01T19:55:00Z",
        symbol="SOL-PERP",
        timeframe="5m",
        side="long",
        size=1.0,
        entry_time="2026-04-01T19:55:00Z",
        entry_price=100.0,
        exit_time="2026-04-01T20:00:00Z",
        exit_price=101.0,
        exit_reason="CLOSE",
        trade_id="good",
    )
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    conn.execute("UPDATE execution_trades SET pnl_usd = -999 WHERE trade_id = ?", ("good",))
    conn.commit()
    conn.close()

    out = scan_execution_ledger_pnl_integrity(db_path=db)
    assert out["violation_count"] == 1
    assert out["examples"]


def test_is_economic_mode() -> None:
    assert is_economic_mode("paper") is True
    assert is_economic_mode("live") is True
    assert is_economic_mode("paper_stub") is False
