"""Phase 1 baseline bridge: same ``market_event_id`` as Anna (canonical 5m bar, single constructor)."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.canonical_bar_refresh import refresh_last_closed_bar_from_ticks  # noqa: E402
from market_data.canonical_time import candle_close_utc_exclusive, last_closed_candle_open_utc  # noqa: E402
from market_data.store import connect_market_db, ensure_market_schema, insert_tick  # noqa: E402
from _paths import repo_root  # noqa: E402


def _seed_closed_sol_bar(market_db: Path) -> str:
    conn = connect_market_db(market_db)
    ensure_market_schema(conn, repo_root())
    now = datetime.now(timezone.utc)
    last_open = last_closed_candle_open_utc(now)
    close_ex = candle_close_utc_exclusive(last_open)
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
    conn.close()
    assert out["ok"] is True
    return str(out["market_event_id"])


def test_baseline_and_anna_share_market_event_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    market_db = tmp_path / "market_data.db"
    ledger_db = tmp_path / "execution_ledger.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(ledger_db))
    monkeypatch.setenv("ANNA_PARALLEL_STRATEGY_IDS", "jupiter_supertrend_ema_rsi_atr_v1")

    mid = _seed_closed_sol_bar(market_db)

    from modules.anna_training.baseline_ledger_bridge import (
        run_baseline_ledger_bridge_tick,
        verify_market_event_id_matches_canonical_bar,
    )
    from modules.anna_training.execution_ledger import query_trades_by_market_event_id
    from modules.anna_training.parallel_strategy_runner import run_parallel_anna_strategies_tick
    from market_data.bar_lookup import fetch_latest_bar_row

    anna = run_parallel_anna_strategies_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    assert anna.get("ok") is True
    assert anna.get("market_event_id") == mid

    base = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    assert base.get("ok") is True
    assert base.get("market_event_id") == mid
    assert base.get("mode") == "paper"

    rows = query_trades_by_market_event_id(mid, db_path=ledger_db)
    assert len(rows) == 2
    assert {r["market_event_id"] for r in rows} == {mid}
    assert {r["lane"] for r in rows} == {"anna", "baseline"}
    sids = {r["strategy_id"] for r in rows}
    assert "baseline" in sids
    assert "jupiter_supertrend_ema_rsi_atr_v1" in sids
    for r in rows:
        if r["lane"] == "baseline":
            assert r["mode"] == "paper"

    bar = fetch_latest_bar_row(db_path=market_db)
    assert bar is not None
    assert verify_market_event_id_matches_canonical_bar(bar) == mid

    base2 = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    assert base2.get("idempotent_skip") is True
    assert len(query_trades_by_market_event_id(mid, db_path=ledger_db)) == 2


def test_corrupt_stored_market_event_id_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    market_db = tmp_path / "market_data.db"
    ledger_db = tmp_path / "execution_ledger.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(ledger_db))
    monkeypatch.setenv("ANNA_PARALLEL_STRATEGY_IDS", "jupiter_supertrend_ema_rsi_atr_v1")

    _seed_closed_sol_bar(market_db)

    conn = sqlite3.connect(market_db)
    conn.execute(
        """
        UPDATE market_bars_5m
        SET market_event_id = 'SOL-PERP_5m_1999-01-01T00:00:00Z'
        WHERE market_event_id IS NOT NULL
        """
    )
    conn.commit()
    conn.close()

    from market_data.bar_lookup import fetch_latest_bar_row
    from modules.anna_training.baseline_ledger_bridge import verify_market_event_id_matches_canonical_bar
    from modules.anna_training.parallel_strategy_runner import run_parallel_anna_strategies_tick

    bar = fetch_latest_bar_row(db_path=market_db)
    assert bar is not None
    with pytest.raises(ValueError, match="divergence"):
        verify_market_event_id_matches_canonical_bar(bar)

    anna = run_parallel_anna_strategies_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    assert anna.get("ok") is False
    assert anna.get("reason") == "market_event_id_divergence"
