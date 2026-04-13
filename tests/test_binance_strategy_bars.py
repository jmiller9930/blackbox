"""Jupiter_3-only ``binance_strategy_bars_5m`` — V2 / ``market_bars_5m`` unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP, TICK_SYMBOL_SOL_DEFAULT, TIMEFRAME_5M
from market_data.canonical_time import candle_close_utc_exclusive, format_candle_open_iso_z
from market_data.market_event_id import make_market_event_id
from market_data.store import connect_market_db, ensure_market_schema, upsert_binance_strategy_bar_5m
from datetime import datetime, timezone


def _one_bar_open() -> datetime:
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_binance_strategy_bar_roundtrip_and_v3_fetch(tmp_path: Path) -> None:
    db = tmp_path / "market_data.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn)

    op = _one_bar_open()
    close_b = candle_close_utc_exclusive(op)
    meid = make_market_event_id(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=op,
        timeframe=TIMEFRAME_5M,
    )
    upsert_binance_strategy_bar_5m(
        conn,
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        tick_symbol=TICK_SYMBOL_SOL_DEFAULT,
        timeframe=TIMEFRAME_5M,
        candle_open_utc=format_candle_open_iso_z(op),
        candle_close_utc=format_candle_open_iso_z(close_b),
        market_event_id=meid,
        open_px=100.0,
        high_px=101.0,
        low_px=99.0,
        close_px=100.5,
        volume_base_asset=1234.5,
        quote_volume_usdt=123456.0,
    )
    conn.close()

    from market_data.bar_lookup import (
        fetch_latest_bar_row_binance_strategy,
        fetch_recent_bars_asc,
        fetch_recent_bars_asc_binance_strategy,
    )

    v2 = fetch_recent_bars_asc(limit=10, db_path=db)
    assert v2 == []

    b3 = fetch_recent_bars_asc_binance_strategy(limit=50, db_path=db)
    assert len(b3) == 1
    assert b3[0]["market_event_id"] == meid
    assert b3[0]["volume_base"] == pytest.approx(1234.5)
    assert b3[0]["strategy_bar_source"] == "binance_5m_ohlcv"
    assert "binance_klines_strategy" in str(b3[0].get("price_source") or "")

    latest = fetch_latest_bar_row_binance_strategy(db_path=db)
    assert latest is not None
    assert latest["close"] == pytest.approx(100.5)


def test_jupiter3_lookback_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    from market_data.bar_lookup import jupiter3_binance_strategy_lookback

    monkeypatch.setenv("BLACKBOX_JUPITER3_BINANCE_LOOKBACK", "5000")
    assert jupiter3_binance_strategy_lookback() == 1200
    monkeypatch.setenv("BLACKBOX_JUPITER3_BINANCE_LOOKBACK", "100")
    assert jupiter3_binance_strategy_lookback() == 100
