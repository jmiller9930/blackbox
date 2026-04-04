"""Canonical 5m bar layer, market_event_id, and tick→bar rollup."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.canonical_bar import build_canonical_bar_from_ticks  # noqa: E402
from market_data.canonical_bar_refresh import refresh_last_closed_bar_from_ticks  # noqa: E402
from market_data.canonical_instrument import (  # noqa: E402
    CANONICAL_INSTRUMENT_SOL_PERP,
    TIMEFRAME_5M,
    canonical_symbol_for_tick_symbol,
)
from market_data.canonical_time import (  # noqa: E402
    candle_close_utc_exclusive,
    floor_utc_to_5m_open,
    format_candle_open_iso_z,
    last_closed_candle_open_utc,
)
from market_data.market_event_id import (  # noqa: E402
    is_valid_market_event_id_format,
    make_market_event_id,
    parse_market_event_id,
)
from market_data.store import (  # noqa: E402
    connect_market_db,
    ensure_market_schema,
    fetch_bar_by_market_event_id,
    insert_tick,
    upsert_market_bar_5m,
)
from market_data.canonical_bar import CanonicalBarV1  # noqa: E402
from _paths import repo_root  # noqa: E402


def test_floor_utc_to_5m_open():
    dt = datetime(2026, 4, 1, 19, 57, 30, tzinfo=timezone.utc)
    assert floor_utc_to_5m_open(dt) == datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)


def test_exclusive_close_boundary():
    op = datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)
    cl = candle_close_utc_exclusive(op)
    assert cl == datetime(2026, 4, 1, 20, 0, 0, tzinfo=timezone.utc)
    assert format_candle_open_iso_z(op) == "2026-04-01T19:55:00Z"


def test_market_event_id_roundtrip():
    op = datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)
    mid = make_market_event_id(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=op,
        timeframe=TIMEFRAME_5M,
    )
    assert mid == "SOL-PERP_5m_2026-04-01T19:55:00Z"
    assert is_valid_market_event_id_format(mid)
    p = parse_market_event_id(mid)
    assert p is not None
    assert p[0] == "SOL-PERP"
    assert p[1] == "5m"
    assert p[2] == "2026-04-01T19:55:00Z"


def test_canonical_symbol_mapping():
    assert canonical_symbol_for_tick_symbol("SOL-USD") == CANONICAL_INSTRUMENT_SOL_PERP


def test_build_ohlc_from_ticks():
    op = datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)
    ticks = [
        {
            "primary_price": 100.0,
            "inserted_at": "2026-04-01T19:55:01Z",
        },
        {
            "primary_price": 102.0,
            "inserted_at": "2026-04-01T19:56:00Z",
        },
        {
            "primary_price": 101.0,
            "inserted_at": "2026-04-01T19:59:00Z",
        },
    ]
    bar = build_canonical_bar_from_ticks(
        ticks=ticks,
        tick_symbol="SOL-USD",
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=op,
    )
    assert bar is not None
    assert bar.open == 100.0
    assert bar.high == 102.0
    assert bar.low == 100.0
    assert bar.close == 101.0
    assert bar.tick_count == 3


def test_rollup_refresh_integration(tmp_path):
    db = tmp_path / "market_data.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())

    now = datetime.now(timezone.utc)
    last_open = last_closed_candle_open_utc(now)
    close_ex = candle_close_utc_exclusive(last_open)
    assert last_open < now
    assert close_ex <= now

    # Ticks inside the last closed bucket [last_open, close_ex) for SOL-USD
    for i, p in enumerate([100.0, 101.0, 99.5]):
        ts = last_open + timedelta(minutes=1) + timedelta(seconds=i * 20)
        assert ts < close_ex
        ins = ts.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        insert_tick(
            conn,
            symbol="SOL-USD",
            inserted_at=ins,
            primary_source="pyth",
            primary_price=p,
            primary_observed_at=ins,
            primary_publish_time=None,
            primary_raw=None,
            comparator_source="cb",
            comparator_price=p,
            comparator_observed_at=ins,
            comparator_raw=None,
            gate_state="ok",
            gate_reason="ok",
        )

    out = refresh_last_closed_bar_from_ticks(conn, "SOL-USD")
    assert out["ok"] is True
    mid = out["market_event_id"]
    row = fetch_bar_by_market_event_id(conn, mid)
    assert row is not None
    assert row["open"] == 100.0
    assert row["close"] == 99.5
    assert row["canonical_symbol"] == CANONICAL_INSTRUMENT_SOL_PERP
    conn.close()


def test_upsert_idempotent(tmp_path):
    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    op = datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)
    meid = make_market_event_id(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=op,
    )
    bar = CanonicalBarV1(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        tick_symbol="SOL-USD",
        timeframe=TIMEFRAME_5M,
        candle_open_utc=op,
        candle_close_utc=candle_close_utc_exclusive(op),
        market_event_id=meid,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        tick_count=1,
        volume_base=None,
        price_source="pyth_primary",
    )
    upsert_market_bar_5m(conn, bar)
    upsert_market_bar_5m(conn, bar)
    r = fetch_bar_by_market_event_id(conn, meid)
    assert r["close"] == 1.5
    conn.close()
