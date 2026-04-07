"""policy_evaluations table — per-bar baseline outcome for backtest joins."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RUNTIME = ROOT / "scripts" / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))


def test_upsert_policy_evaluation_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "execution_ledger.db"
    from modules.anna_training.execution_ledger import (
        ensure_execution_ledger_schema,
        upsert_policy_evaluation,
    )

    conn = sqlite3.connect(db)
    ensure_execution_ledger_schema(conn)
    mid = "SOL-PERP_5m_2026-04-01T12:00:00Z"
    feats = {"reference": "test", "x": 1}
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode="sean_jupiter_v1",
        tick_mode="paper",
        trade=False,
        reason_code="no_signal",
        features=feats,
        side="flat",
        db_path=db,
    )
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode="sean_jupiter_v1",
        tick_mode="paper",
        trade=False,
        reason_code="no_signal",
        features=feats,
        side="flat",
        db_path=db,
    )
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM policy_evaluations").fetchone()[0]
    assert n == 1
    row = conn.execute(
        "SELECT trade, reason_code, side FROM policy_evaluations WHERE market_event_id = ?",
        (mid,),
    ).fetchone()
    assert row[0] == 0
    assert row[1] == "no_signal"
    assert row[2] == "flat"
    conn.close()


def test_baseline_bridge_writes_policy_eval_legacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKET_BAR_MEMBERSHIP", "inserted_at")
    market_db = tmp_path / "market_data.db"
    ledger_db = tmp_path / "execution_ledger.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(ledger_db))
    monkeypatch.setenv("BLACKBOX_MARKET_DATA_PATH", str(market_db))
    monkeypatch.setenv("BASELINE_LEDGER_BRIDGE", "1")
    monkeypatch.setenv("BASELINE_LEDGER_SIGNAL_MODE", "legacy_mechanical_long")

    sys.path.insert(0, str(ROOT / "scripts" / "runtime"))
    from market_data.canonical_time import candle_close_utc_exclusive, last_closed_candle_open_utc  # noqa: E402
    from market_data.store import connect_market_db, ensure_market_schema, insert_tick  # noqa: E402
    from market_data.canonical_bar_refresh import refresh_last_closed_bar_from_ticks  # noqa: E402
    from market_data.bar_lookup import fetch_latest_bar_row  # noqa: E402


    from _paths import repo_root  # noqa: E402

    from datetime import datetime, timedelta, timezone

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
    mid = str(out["market_event_id"])

    from modules.anna_training.baseline_ledger_bridge import run_baseline_ledger_bridge_tick  # noqa: E402

    r = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    assert r.get("ok") is True
    bar = fetch_latest_bar_row(db_path=market_db)
    assert bar is not None
    assert str(bar.get("market_event_id")) == mid

    lconn = sqlite3.connect(ledger_db)
    prow = lconn.execute(
        "SELECT trade, reason_code, side, features_json FROM policy_evaluations WHERE market_event_id = ?",
        (mid,),
    ).fetchone()
    assert prow is not None
    assert prow[0] == 1
    assert prow[1] == "legacy_mechanical_long"
    assert prow[2] == "long"
    assert json.loads(prow[3]).get("economic_basis") == "canonical_bar_open_to_close_long_1unit"
    pe = lconn.execute(
        "SELECT COUNT(*), MIN(event_type), MAX(event_type) FROM position_events WHERE market_event_id = ?",
        (mid,),
    ).fetchone()
    assert pe[0] == 2
    types = {r[0] for r in lconn.execute("SELECT event_type FROM position_events WHERE market_event_id = ?", (mid,))}
    assert types == {"position_open", "position_close"}
    lconn.close()
