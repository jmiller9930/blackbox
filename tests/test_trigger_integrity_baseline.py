"""
Trigger integrity — baseline Jupiter policy_evaluations vs lifecycle (sandbox proof).

Operator / architect standard (see directive): for a qualifying evaluator outcome
(``would_trade`` / ``sig.trade`` true), the persisted ``policy_evaluations`` row must
record matching semantics, and any ``would_trade=true`` + ``did_trade=false`` pair
must carry an explicit ``reason_code`` (not inferred later).

These tests exercise :func:`modules.anna_training.baseline_ledger_bridge.run_baseline_ledger_bridge_tick`
with a **known qualifying** mocked signal (``trade=True``) and SQLite temp DBs — end-to-end
from evaluator stub → ``features_json`` → operator-visible fields via
``_operator_trade_semantics_from_policy_row``-equivalent assertions.

Allowed reasons for ``would_trade=true`` and ``did_trade=false`` in **normal** baseline
operation are **finite** and listed in ``baseline_ledger_bridge`` module docstring
(``jupiter_2_baseline_holding``, ``jupiter_2_baseline_exit``). Legacy rows without
``features_json.would_trade`` remain ``Qualifies: n/a`` until backfilled (product choice).
"""

from __future__ import annotations

import json
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


def _seed_closed_sol_bar(market_db: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("BASELINE_LEDGER_AFTER_CANONICAL_BAR", "0")
    monkeypatch.setenv("BLACKBOX_BINANCE_KLINE_ENABLED", "0")
    monkeypatch.setenv("MARKET_BAR_MEMBERSHIP", "inserted_at")
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


def _policy_semantics_from_row(prow: sqlite3.Row) -> dict[str, object]:
    """Mirror ``dashboard_bundle._operator_trade_semantics_from_policy_row`` inputs from SQL."""
    from modules.anna_training.dashboard_bundle import _operator_trade_semantics_from_policy_row

    pol = {
        "trade": bool(prow[0]),
        "reason_code": str(prow[1] or ""),
        "features": json.loads(prow[2]) if prow[2] else {},
    }
    return _operator_trade_semantics_from_policy_row(pol)


def test_trigger_integrity_qualifying_bar_opens_and_persists_would_did_trade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evaluator trade=True → persisted would_trade/did_trade true → lifecycle opened."""
    market_db = tmp_path / "market_data.db"
    ledger_db = tmp_path / "execution_ledger.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(ledger_db))
    monkeypatch.setenv("BASELINE_LEDGER_BRIDGE", "1")
    monkeypatch.setenv("BASELINE_LEDGER_SIGNAL_MODE", "sean_jupiter_v1")
    monkeypatch.setenv("BASELINE_POLICY_EVALUATION_LOG", "1")

    mid = _seed_closed_sol_bar(market_db, monkeypatch)

    from modules.anna_training.baseline_ledger_bridge import run_baseline_ledger_bridge_tick
    from modules.anna_training.sean_jupiter_baseline_signal import SeanJupiterBaselineSignalV1

    def _qualifying_eval(*_a: object, **_k: object) -> SeanJupiterBaselineSignalV1:
        return SeanJupiterBaselineSignalV1(
            trade=True,
            side="long",
            reason_code="trigger_integrity_fixture_open",
            pnl_usd=None,
            features={"reference": "trigger_integrity", "free_collateral_usd": 1000.0},
        )

    monkeypatch.setattr(
        "modules.anna_training.sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v1",
        _qualifying_eval,
    )

    r = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    assert r.get("ok") is True
    assert r.get("lifecycle") == "opened"
    assert r.get("market_event_id") == mid

    lconn = sqlite3.connect(ledger_db)
    lconn.row_factory = sqlite3.Row
    prow = lconn.execute(
        "SELECT trade, reason_code, features_json FROM policy_evaluations WHERE market_event_id = ?",
        (mid,),
    ).fetchone()
    assert prow is not None
    assert prow["trade"] == 1
    feats = json.loads(prow["features_json"])
    assert feats.get("would_trade") is True
    assert feats.get("did_trade") is True
    assert prow["reason_code"] == "trigger_integrity_fixture_open"
    sem = _policy_semantics_from_row(prow)
    assert sem["would_trade"] is True
    assert sem["did_trade"] is True
    lconn.close()


def test_trigger_integrity_would_trade_true_did_trade_false_records_holding_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second tick on same bar: qualifying signal but no new entry — explicit holding reason_code."""
    market_db = tmp_path / "market_data.db"
    ledger_db = tmp_path / "execution_ledger.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(ledger_db))
    monkeypatch.setenv("BASELINE_LEDGER_BRIDGE", "1")
    monkeypatch.setenv("BASELINE_LEDGER_SIGNAL_MODE", "sean_jupiter_v1")
    monkeypatch.setenv("BASELINE_POLICY_EVALUATION_LOG", "1")

    mid = _seed_closed_sol_bar(market_db, monkeypatch)

    from modules.anna_training.baseline_ledger_bridge import run_baseline_ledger_bridge_tick
    from modules.anna_training.sean_jupiter_baseline_signal import SeanJupiterBaselineSignalV1

    def _qualifying_eval(*_a: object, **_k: object) -> SeanJupiterBaselineSignalV1:
        return SeanJupiterBaselineSignalV1(
            trade=True,
            side="long",
            reason_code="trigger_integrity_fixture_open",
            pnl_usd=None,
            features={"reference": "trigger_integrity", "free_collateral_usd": 1000.0},
        )

    monkeypatch.setattr(
        "modules.anna_training.sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v1",
        _qualifying_eval,
    )

    r1 = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    assert r1.get("lifecycle") == "opened"
    r2 = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    assert r2.get("lifecycle_idempotent") is True

    lconn = sqlite3.connect(ledger_db)
    lconn.row_factory = sqlite3.Row
    prow = lconn.execute(
        "SELECT trade, reason_code, features_json FROM policy_evaluations WHERE market_event_id = ?",
        (mid,),
    ).fetchone()
    assert prow is not None
    feats = json.loads(prow["features_json"])
    assert feats.get("would_trade") is True
    assert feats.get("did_trade") is False
    assert prow["reason_code"] == "jupiter_2_baseline_holding"
    sem = _policy_semantics_from_row(prow)
    assert sem["would_trade"] is True
    assert sem["did_trade"] is False
    lconn.close()
