"""SQLite lock resilience + policy_evaluations persistence (directive: no silent drops)."""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.canonical_bar_refresh import refresh_last_closed_bar_from_ticks  # noqa: E402
from market_data.canonical_time import FIVE_MINUTES, candle_close_utc_exclusive  # noqa: E402
from market_data.store import connect_market_db, ensure_market_schema, insert_tick  # noqa: E402
from _paths import repo_root  # noqa: E402


def test_sqlite_retry_on_locked_eventually_succeeds(tmp_path: Path) -> None:
    from modules.anna_training.execution_ledger import sqlite_retry_on_locked

    db = tmp_path / "x.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t(i INTEGER PRIMARY KEY)")
    conn.commit()

    phase = {"n": 0}

    def op() -> None:
        phase["n"] += 1
        if phase["n"] < 4:
            raise sqlite3.OperationalError("database is locked")
        conn.execute("INSERT INTO t VALUES (1)")

    sqlite_retry_on_locked(op, label="unit_retry_test", attempts=12)
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    conn.close()


def _insert_ticks_for_bucket(
    conn: sqlite3.Connection,
    *,
    candle_open: datetime,
    prices: list[float],
) -> None:
    close_ex = candle_close_utc_exclusive(candle_open)
    for i, p in enumerate(prices):
        ts = candle_open + timedelta(minutes=1) + timedelta(seconds=i * 15)
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


def test_n_consecutive_closed_bars_each_get_policy_evaluation_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate N sequential last-closed buckets; each materialized bar yields one policy_evaluations row."""
    market_db = tmp_path / "market_data.db"
    ledger_db = tmp_path / "execution_ledger.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(ledger_db))
    monkeypatch.setenv("BASELINE_LEDGER_AFTER_CANONICAL_BAR", "1")
    monkeypatch.setenv("BLACKBOX_BINANCE_KLINE_ENABLED", "0")
    monkeypatch.setenv("MARKET_BAR_MEMBERSHIP", "inserted_at")
    monkeypatch.setenv("BASELINE_LEDGER_BRIDGE", "1")
    monkeypatch.setenv("BASELINE_POLICY_EVALUATION_LOG", "1")

    from modules.anna_training.sean_jupiter_baseline_signal import SeanJupiterBaselineSignalV1

    def _flat_eval(*_a: object, **_k: object) -> SeanJupiterBaselineSignalV1:
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="persistence_harness_flat",
            pnl_usd=None,
            features={"reference": "persistence_harness"},
        )

    monkeypatch.setattr(
        "modules.anna_training.sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v1",
        _flat_eval,
    )
    monkeypatch.setattr(
        "modules.anna_training.sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v3",
        _flat_eval,
    )
    monkeypatch.setattr(
        "modules.anna_training.sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v4",
        _flat_eval,
    )

    base = datetime(2030, 6, 1, 15, 0, tzinfo=timezone.utc)
    n = 5
    opens = [base + i * FIVE_MINUTES for i in range(n)]

    conn = connect_market_db(market_db)
    ensure_market_schema(conn, repo_root())

    seen_mids: list[str] = []

    for i, op in enumerate(opens):
        monkeypatch.setattr(
            "market_data.canonical_bar_refresh.last_closed_candle_open_utc",
            lambda _op=op: _op,
        )
        _insert_ticks_for_bucket(conn, candle_open=op, prices=[100.0 + i, 100.5 + i, 99.8 + i])
        out = refresh_last_closed_bar_from_ticks(conn, "SOL-USD")
        assert out.get("ok") is True, out
        mid = str(out.get("market_event_id") or "")
        assert mid
        seen_mids.append(mid)

    conn.close()

    lconn = sqlite3.connect(str(ledger_db))
    for mid in seen_mids:
        c = lconn.execute(
            "SELECT COUNT(*) FROM policy_evaluations WHERE market_event_id = ?",
            (mid,),
        ).fetchone()[0]
        assert int(c) == 1, f"missing policy_evaluations row for {mid!r}"
    lconn.close()


def test_bridge_tick_retries_when_ledger_database_is_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exclusive lock on execution_ledger.db is released; bridge + upsert must complete (retries)."""
    market_db = tmp_path / "market_data.db"
    ledger_db = tmp_path / "execution_ledger.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(ledger_db))
    monkeypatch.setenv("BASELINE_LEDGER_AFTER_CANONICAL_BAR", "0")
    monkeypatch.setenv("BLACKBOX_BINANCE_KLINE_ENABLED", "0")
    monkeypatch.setenv("MARKET_BAR_MEMBERSHIP", "inserted_at")
    monkeypatch.setenv("BASELINE_LEDGER_BRIDGE", "1")
    monkeypatch.setenv("BASELINE_POLICY_EVALUATION_LOG", "1")

    conn = connect_market_db(market_db)
    ensure_market_schema(conn, repo_root())
    op = datetime(2031, 3, 3, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "market_data.canonical_bar_refresh.last_closed_candle_open_utc",
        lambda: op,
    )
    _insert_ticks_for_bucket(conn, candle_open=op, prices=[101.0, 102.0, 100.0])
    out = refresh_last_closed_bar_from_ticks(conn, "SOL-USD")
    conn.close()
    assert out.get("ok") is True
    mid = str(out["market_event_id"])

    from modules.anna_training.baseline_ledger_bridge import run_baseline_ledger_bridge_tick
    from modules.anna_training.sean_jupiter_baseline_signal import SeanJupiterBaselineSignalV1

    def _flat_eval(*_a: object, **_k: object) -> SeanJupiterBaselineSignalV1:
        return SeanJupiterBaselineSignalV1(
            trade=False,
            side="flat",
            reason_code="lock_contention_flat",
            pnl_usd=None,
            features={"reference": "lock_contention"},
        )

    monkeypatch.setattr(
        "modules.anna_training.sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v1",
        _flat_eval,
    )
    monkeypatch.setattr(
        "modules.anna_training.sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v3",
        _flat_eval,
    )
    monkeypatch.setattr(
        "modules.anna_training.sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v4",
        _flat_eval,
    )

    hold_ready = threading.Event()

    def _exclusive_holder() -> None:
        c = sqlite3.connect(str(ledger_db), timeout=30.0)
        c.execute("PRAGMA busy_timeout=60000")
        c.execute("BEGIN EXCLUSIVE")
        hold_ready.set()
        time.sleep(0.35)
        c.commit()
        c.close()

    th = threading.Thread(target=_exclusive_holder, daemon=True)
    th.start()
    assert hold_ready.wait(timeout=5.0)

    r = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    th.join(timeout=10.0)
    assert r.get("ok") is True, r

    lconn = sqlite3.connect(str(ledger_db))
    n = int(
        lconn.execute(
            "SELECT COUNT(*) FROM policy_evaluations WHERE market_event_id = ?",
            (mid,),
        ).fetchone()[0]
    )
    lconn.close()
    assert n == 1
