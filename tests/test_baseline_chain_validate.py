"""Baseline chain validation harness — market / policy / ledger alignment."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_RT = _ROOT / "scripts" / "runtime"
if str(_RT) not in sys.path:
    sys.path.insert(0, str(_RT))

import pytest

from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP, TICK_SYMBOL_SOL_DEFAULT, TIMEFRAME_5M
from market_data.canonical_time import candle_close_utc_exclusive, format_candle_open_iso_z
from market_data.market_event_id import make_market_event_id
from market_data.store import connect_market_db, ensure_market_schema, upsert_binance_strategy_bar_5m
from modules.anna_training.baseline_chain_validate import validate_bar, validate_range
from modules.anna_training.execution_ledger import (
    SIGNAL_MODE_JUPITER_3,
    connect_ledger,
    ensure_execution_ledger_schema,
    upsert_policy_evaluation,
)
from datetime import datetime, timezone


def _bar_open() -> datetime:
    return datetime(2026, 4, 14, 1, 5, 0, tzinfo=timezone.utc)


def _setup_market_db(path: Path) -> str:
    op = _bar_open()
    close_b = candle_close_utc_exclusive(op)
    meid = make_market_event_id(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=op,
        timeframe=TIMEFRAME_5M,
    )
    conn = connect_market_db(path)
    ensure_market_schema(conn)
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
        volume_base_asset=10.0,
        quote_volume_usdt=1000.0,
    )
    conn.close()
    return format_candle_open_iso_z(op)


@pytest.mark.parametrize(
    ("trade", "with_ledger", "expected_code"),
    [
        (False, False, "aligned_no_trade"),
        (True, True, "aligned_trade"),
        (True, False, "misaligned_missed_trade"),
        (False, True, "misaligned_execution_or_recording"),
    ],
)
def test_validate_bar_jup_v3_matrix(
    tmp_path: Path,
    trade: bool,
    with_ledger: bool,
    expected_code: str,
) -> None:
    mdb = tmp_path / "m.db"
    ldb = tmp_path / "l.db"
    co = _setup_market_db(mdb)
    mid = make_market_event_id(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=_bar_open(),
        timeframe=TIMEFRAME_5M,
    )

    conn = connect_ledger(ldb)
    ensure_execution_ledger_schema(conn)
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode=SIGNAL_MODE_JUPITER_3,
        tick_mode="paper",
        trade=trade,
        reason_code="test_reason",
        features={},
        side="long" if trade else "flat",
        conn=conn,
    )
    if with_ledger:
        conn.execute(
            """
            INSERT INTO execution_trades (
              trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
              side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
              pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "t_test1",
                "baseline",
                "baseline",
                "paper",
                mid,
                "SOL-PERP",
                "5m",
                "long",
                co,
                100.0,
                1.0,
                None,
                None,
                None,
                None,
                "{}",
                "",
                None,
                "execution_trade_v1",
                "2026-04-14T01:06:00Z",
            ),
        )
    conn.commit()
    conn.close()

    out = validate_bar(
        co,
        policy_slot="jup_v3",
        market_db_path=mdb,
        ledger_db_path=ldb,
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
    )
    st = out["structured"]
    assert st["verdict_code"] == expected_code


def test_validate_bar_incomplete_no_policy(tmp_path: Path) -> None:
    mdb = tmp_path / "m.db"
    ldb = tmp_path / "l.db"
    co = _setup_market_db(mdb)
    conn = connect_ledger(ldb)
    ensure_execution_ledger_schema(conn)
    conn.commit()
    conn.close()
    out = validate_bar(co, policy_slot="jup_v3", market_db_path=mdb, ledger_db_path=ldb)
    assert out["structured"]["verdict_code"] == "incomplete_data"


def test_validate_range_last_n_aggregate(tmp_path: Path) -> None:
    mdb = tmp_path / "m.db"
    ldb = tmp_path / "l.db"
    co = _setup_market_db(mdb)
    mid = make_market_event_id(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=_bar_open(),
        timeframe=TIMEFRAME_5M,
    )
    conn = connect_ledger(ldb)
    ensure_execution_ledger_schema(conn)
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode=SIGNAL_MODE_JUPITER_3,
        tick_mode="paper",
        trade=False,
        reason_code="idle",
        features={},
        side="flat",
        conn=conn,
    )
    conn.commit()
    conn.close()

    out = validate_range(
        mode="last_n",
        policy_slot="jup_v3",
        last_n=3,
        market_db_path=mdb,
        ledger_db_path=ldb,
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
    )
    assert out["aggregate"]["verdict_code"] == "aligned"
    assert len(out["bars"]) >= 1
