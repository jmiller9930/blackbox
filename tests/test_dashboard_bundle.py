"""Smoke tests for dashboard bundle (trade chain + aggregate)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from modules.anna_training.execution_ledger import (
    connect_ledger,
    ensure_execution_ledger_schema,
    upsert_policy_evaluation,
)
from modules.anna_training.dashboard_bundle import (
    BASELINE_TRADES_REPORT_SCHEMA,
    build_baseline_active_position_snapshot,
    _compact_baseline_cell_policy_bound,
    _event_axis_jupiter_tile_narratives,
    _pair_vs_baseline_for_cells,
    _strip_outcome_from_pnl,
    build_baseline_trades_report,
    build_dashboard_bundle,
    build_trade_chain_payload,
)


def test_build_trade_chain_payload_schema() -> None:
    tc = build_trade_chain_payload(max_events=8)
    assert tc.get("schema") == "blackbox_trade_chain_v1"
    assert "event_axis" in tc
    assert "event_axis_time_utc_iso" in tc
    axis = tc["event_axis"]
    times = tc["event_axis_time_utc_iso"]
    assert isinstance(axis, list)
    assert isinstance(times, list)
    assert len(times) == len(axis)
    assert "rows" in tc
    assert isinstance(tc["rows"], list)
    assert "scorecard" in tc
    assert isinstance(tc["scorecard"], list)
    assert len(tc["scorecard"]) == len(tc["rows"])
    assert "anna_vs_baseline_aggregate" in tc
    assert isinstance(tc["anna_vs_baseline_aggregate"], dict)
    assert "market_clock" in tc
    assert tc["rows"][0].get("chain_kind") == "baseline"
    assert tc["rows"][0].get("row_tier") == "primary"
    assert (tc.get("recency") or {}).get("axis_order") == "oldest_left_newest_right"
    assert tc.get("jupiter_tile_narrative_schema") == "jupiter_tile_narrative_v1"
    assert "recent_baseline_trades" in tc
    assert isinstance(tc["recent_baseline_trades"], list)
    for row in tc["recent_baseline_trades"]:
        assert set(row.keys()) >= {
            "market_event_id",
            "side",
            "time_utc_iso",
            "outcome",
            "pnl_usd",
        }
    assert "baseline_trades_report_rows" in tc
    assert isinstance(tc["baseline_trades_report_rows"], list)
    assert len(tc["baseline_trades_report_rows"]) >= len(tc["recent_baseline_trades"])


def test_build_dashboard_bundle_schema() -> None:
    b = build_dashboard_bundle(max_events=8)
    assert b.get("schema") == "blackbox_dashboard_bundle_v1"
    assert "trade_chain" in b
    assert "sequential" in b
    assert "operational_boundary" in b
    assert "learning_summary" in b
    assert "liveness" in b
    assert b["liveness"].get("update_model", {}).get("dashboard_poll_interval_ms") == 1500
    assert "market_clock" in b
    assert "next_tick" in b["liveness"]
    assert "bundle_snapshot_at" in b["liveness"]
    assert "eta_at" in b["liveness"]["next_tick"]
    assert "paper_capital" in b
    assert "recency" in b["trade_chain"]
    assert "recent_baseline_trades" in b["trade_chain"]
    assert isinstance(b["trade_chain"]["recent_baseline_trades"], list)
    assert "operator_trading" in b
    assert (b["operator_trading"] or {}).get("schema") == "operator_trading_strategy_v1"
    assert "eligible_strategy_ids" in b["operator_trading"]
    assert isinstance(b["operator_trading"]["eligible_strategy_ids"], list)
    iv = b.get("intelligence_visibility")
    assert isinstance(iv, dict)
    assert iv.get("schema") == "anna_intelligence_visibility_v1"
    assert "status_strip" in iv
    for k in ("context", "learning", "llm_analysis", "decisioning", "baseline_comparison"):
        assert k in (iv.get("status_strip") or {})
    assert "effectiveness_summary" in iv
    assert "subsystem_gaps" in iv
    lp = b.get("learning_proof")
    assert isinstance(lp, dict)
    assert lp.get("schema") == "learning_proof_bundle_v1"
    assert "aggregate" in lp
    assert "per_event" in lp
    jp = b.get("jupiter_policy_snapshot")
    assert isinstance(jp, dict)
    assert jp.get("schema") == "jupiter_policy_snapshot_v1"
    assert "signal_readiness" not in jp
    assert "alignment_pills" not in jp


def test_pair_vs_baseline_for_cells() -> None:
    base = {"empty": False, "mode": "paper", "pnl_usd": 1.0, "mae_usd": 0.5}
    win = {"empty": False, "mode": "paper", "pnl_usd": 2.0, "mae_usd": 0.45}
    lose = {"empty": False, "mode": "paper", "pnl_usd": 0.5, "mae_usd": 0.4}
    stub_no_pnl = {"empty": False, "mode": "paper_stub", "pnl_usd": None, "mae_usd": 0.1}
    stub_win = {"empty": False, "mode": "paper_stub", "pnl_usd": 2.0, "mae_usd": 0.45}
    assert _pair_vs_baseline_for_cells(base, win, epsilon=0.05)["vs_baseline"] == "WIN"
    assert _pair_vs_baseline_for_cells(base, lose, epsilon=0.05)["vs_baseline"] == "NOT_WIN"
    assert _pair_vs_baseline_for_cells(base, stub_no_pnl, epsilon=0.05)["vs_baseline"] == "EXCLUDED"
    assert _pair_vs_baseline_for_cells(base, stub_win, epsilon=0.05)["vs_baseline"] == "WIN"


def test_trade_chain_includes_pair_epsilon() -> None:
    tc = build_trade_chain_payload(max_events=4)
    assert "paired_comparison_epsilon" in tc
    assert isinstance(tc["paired_comparison_epsilon"], float)


def test_trade_chain_baseline_requires_policy_eval_not_execution_only(tmp_path: Path) -> None:
    """Baseline WIN/LOSS must not follow execution_trades when policy_evaluations is absent."""
    import modules.anna_training.dashboard_bundle as dbmod

    dbmod._MARKET_DB = None
    ledger = tmp_path / "el.db"
    market = tmp_path / "m.db"
    mid = "SOL-PERP_5m_2026-04-01T12:00:00Z"

    conn_m = sqlite3.connect(market)
    conn_m.execute(
        """CREATE TABLE market_bars_5m (
            id INTEGER PRIMARY KEY,
            canonical_symbol TEXT NOT NULL,
            tick_symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            candle_open_utc TEXT NOT NULL,
            candle_close_utc TEXT NOT NULL,
            market_event_id TEXT NOT NULL UNIQUE,
            open REAL, high REAL, low REAL, close REAL,
            tick_count INTEGER NOT NULL DEFAULT 0,
            volume_base REAL,
            price_source TEXT NOT NULL DEFAULT 'pyth_primary',
            bar_schema_version TEXT NOT NULL DEFAULT 'canonical_bar_v1',
            computed_at TEXT NOT NULL
        )"""
    )
    conn_m.execute(
        """INSERT INTO market_bars_5m (
            canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
            market_event_id, open, high, low, close, tick_count, computed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "SOL-PERP",
            "SOL-PERP",
            "5m",
            "2026-04-01T12:00:00Z",
            "2026-04-01T12:05:00Z",
            mid,
            100.0,
            101.0,
            99.0,
            100.5,
            10,
            "2026-04-01T12:05:01Z",
        ),
    )
    conn_m.commit()
    conn_m.close()

    conn_l = connect_ledger(ledger)
    ensure_execution_ledger_schema(conn_l)
    conn_l.execute(
        """INSERT INTO execution_trades (
            trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
            side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
            pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "bl_test1",
            "baseline",
            "baseline",
            "paper",
            mid,
            "SOL-PERP",
            "5m",
            "long",
            "2026-04-01T12:00:00Z",
            100.0,
            1.0,
            "2026-04-01T12:05:00Z",
            100.5,
            "CLOSE",
            0.5,
            "{}",
            "non-authoritative fixture",
            None,
            "execution_trade_v1",
            "2026-04-01T12:05:02Z",
        ),
    )
    conn_l.commit()
    conn_l.close()

    tc = build_trade_chain_payload(db_path=ledger, market_db_path=market, max_events=8)
    assert tc.get("event_axis_source") == "market_bars_5m"
    baseline = next(r for r in tc["rows"] if r["chain_kind"] == "baseline")
    assert baseline["cells"][mid]["outcome"] == "NO_TRADE"
    assert baseline["cells"][mid].get("ledger_row_ignored") is True


def test_jupiter_tile_narrative_authoritative_from_ledger_without_tile(
    tmp_path: Path,
) -> None:
    """Policy row wins even when ``features`` has no ``tile`` (no silent bar recompute)."""
    import modules.anna_training.dashboard_bundle as dbmod

    dbmod._MARKET_DB = None
    mid = "SOL-PERP_5m_LEDGER_STUB_EVENT"

    market = tmp_path / "m.db"
    conn_m = sqlite3.connect(market)
    conn_m.execute(
        """CREATE TABLE market_bars_5m (
            id INTEGER PRIMARY KEY,
            canonical_symbol TEXT NOT NULL,
            tick_symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            candle_open_utc TEXT NOT NULL,
            candle_close_utc TEXT NOT NULL,
            market_event_id TEXT NOT NULL UNIQUE,
            open REAL, high REAL, low REAL, close REAL,
            tick_count INTEGER NOT NULL DEFAULT 0,
            volume_base REAL,
            price_source TEXT NOT NULL DEFAULT 'pyth_primary',
            bar_schema_version TEXT NOT NULL DEFAULT 'canonical_bar_v1',
            computed_at TEXT NOT NULL
        )"""
    )
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(220):
        co = (base + timedelta(minutes=5 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cc = (base + timedelta(minutes=5 * i + 5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        meid = mid if i == 219 else f"SOL-PERP_5m_fill_{i}"
        conn_m.execute(
            """INSERT INTO market_bars_5m (
                canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
                market_event_id, open, high, low, close, tick_count, computed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "SOL-PERP",
                "SOL-PERP",
                "5m",
                co,
                cc,
                meid,
                100.0 + i * 0.01,
                101.0 + i * 0.01,
                99.0 + i * 0.01,
                100.5 + i * 0.01,
                10,
                cc,
            ),
        )
    conn_m.commit()
    conn_m.close()

    ledger = tmp_path / "el.db"
    conn_l = connect_ledger(ledger)
    ensure_execution_ledger_schema(conn_l)
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode="sean_jupiter_v1",
        tick_mode="paper",
        trade=False,
        reason_code="ledger_authoritative_fixture",
        features={},
        conn=conn_l,
    )
    narr = _event_axis_jupiter_tile_narratives(conn_l, [mid], market)
    conn_l.close()

    text = narr.get(mid, "")
    assert "ledger_authoritative_fixture" in text
    assert "New 5-min candle formed" not in text


def test_strip_outcome_zero_is_flat_not_win() -> None:
    assert _strip_outcome_from_pnl(0) == "FLAT"
    assert _strip_outcome_from_pnl(0.0) == "FLAT"
    assert _strip_outcome_from_pnl(1e-10) == "FLAT"
    assert _strip_outcome_from_pnl(-1e-10) == "FLAT"
    assert _strip_outcome_from_pnl(1e-8) == "WIN"
    assert _strip_outcome_from_pnl(-1e-8) == "LOSS"


def test_compact_baseline_held_shows_held_not_no_trade(tmp_path: Path) -> None:
    """Mid-lifecycle bars: policy trade=0 + holding reason → **held** (not NO_TRADE)."""
    ledger = tmp_path / "el.db"
    mid = "SOL-PERP_5m_2026-04-01T12:00:00Z"
    conn = connect_ledger(ledger)
    ensure_execution_ledger_schema(conn)
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode="sean_jupiter_v1",
        tick_mode="paper",
        trade=False,
        reason_code="jupiter_2_baseline_holding",
        features={"lifecycle": "holding"},
        side="long",
        conn=conn,
    )
    conn.commit()
    cell = _compact_baseline_cell_policy_bound(conn, mid, None, market_db_path=None)
    conn.close()
    assert cell["outcome"] == "HELD"
    assert cell.get("baseline_lifecycle_phase") == "held"
    assert cell.get("outcome_display") == "held"
    assert cell.get("baseline_display_reason") == "lifecycle_held"
    assert cell.get("empty") is False


def test_compact_baseline_open_entry_no_ledger_row(tmp_path: Path) -> None:
    """Entry bar: trade=1, no execution_trades row yet → **open** (lifecycle)."""
    ledger = tmp_path / "el.db"
    mid = "SOL-PERP_5m_2026-04-01T11:55:00Z"
    conn = connect_ledger(ledger)
    ensure_execution_ledger_schema(conn)
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode="sean_jupiter_v1",
        tick_mode="paper",
        trade=True,
        reason_code="jupiter_2_sean_signal_ok",
        features={"tile": {}},
        side="long",
        conn=conn,
    )
    conn.commit()
    cell = _compact_baseline_cell_policy_bound(conn, mid, None, market_db_path=None)
    conn.close()
    assert cell["outcome"] == "OPEN"
    assert cell.get("baseline_lifecycle_phase") == "open"
    assert cell.get("outcome_display") == "open"
    assert cell.get("baseline_display_reason") == "lifecycle_entry_open"


def test_compact_baseline_exit_shows_win_from_ledger_when_policy_trade_false(tmp_path: Path) -> None:
    """Exit bar: trade=0 + jupiter_2_baseline_exit + closing row → WIN/LOSS from ledger."""
    ledger = tmp_path / "el.db"
    mid = "SOL-PERP_5m_2026-04-01T12:05:00Z"
    conn = connect_ledger(ledger)
    ensure_execution_ledger_schema(conn)
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode="sean_jupiter_v1",
        tick_mode="paper",
        trade=False,
        reason_code="jupiter_2_baseline_exit",
        features={"lifecycle": "exit"},
        side="long",
        conn=conn,
    )
    conn.execute(
        """INSERT INTO execution_trades (
            trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
            side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
            pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "bl_exit1",
            "baseline",
            "baseline",
            "paper",
            mid,
            "SOL-PERP",
            "5m",
            "long",
            "2026-04-01T12:00:00Z",
            100.0,
            1.0,
            "2026-04-01T12:05:00Z",
            101.0,
            "TAKE_PROFIT",
            1.0,
            "{}",
            "",
            None,
            "execution_trade_v1",
            "2026-04-01T12:05:02Z",
        ),
    )
    conn.commit()
    ledger_row = {
        "trade_id": "bl_exit1",
        "strategy_id": "baseline",
        "lane": "baseline",
        "mode": "paper",
        "market_event_id": mid,
        "symbol": "SOL-PERP",
        "timeframe": "5m",
        "side": "long",
        "entry_time": "2026-04-01T12:00:00Z",
        "entry_price": 100.0,
        "size": 1.0,
        "exit_time": "2026-04-01T12:05:00Z",
        "exit_price": 101.0,
        "exit_reason": "TAKE_PROFIT",
        "pnl_usd": 1.0,
        "created_at_utc": "2026-04-01T12:05:02Z",
        "trace_id": None,
        "notes": "",
        "context_snapshot_json": "{}",
    }
    cell = _compact_baseline_cell_policy_bound(conn, mid, ledger_row, market_db_path=None)
    conn.close()
    assert cell.get("baseline_display_reason") == "lifecycle_exit_execution"
    assert cell["outcome"] == "WIN"
    assert cell.get("baseline_lifecycle_phase") == "closed"
    assert cell.get("outcome_display") == "closed win"
    assert cell.get("policy_trade") is False


def test_build_baseline_trades_report_schema() -> None:
    rep = build_baseline_trades_report(limit=10, scope="all")
    assert rep.get("schema") == BASELINE_TRADES_REPORT_SCHEMA
    assert "rows" in rep and isinstance(rep["rows"], list)
    assert "meta" in rep and isinstance(rep["meta"], dict)
    assert rep["meta"].get("scope") == "all"
    assert rep["meta"].get("report_note")
    ap = rep["meta"].get("active_position")
    assert isinstance(ap, dict)
    assert "position_open" in ap
    assert ap.get("schema") == "blackbox_baseline_active_position_v1"
    snap = build_baseline_active_position_snapshot()
    assert snap.get("schema") == "blackbox_baseline_active_position_v1"
    assert "position_open" in snap
    assert "direction_summary" in rep["meta"]
    assert "long_count" in rep["meta"]["direction_summary"]
    assert "pnl_semantics" in rep["meta"]
    assert rep["meta"]["pnl_semantics"].get("fees_included") is False
    for row in rep["rows"]:
        assert "baseline_authority" in row
        assert row["baseline_authority"] in ("TRADE", "NO_TRADE")
        assert "baseline_authority_reason" in row
        assert "lifecycle_open_at_utc" in row
        assert "lifecycle_closed_label" in row
        assert "held_display" in row
        assert "stop_loss_entry_price" in row
        assert "take_profit_entry_price" in row
        assert "stop_loss_exit_price" in row
        assert "take_profit_exit_price" in row
        assert "operator_trade_snapshot" in row
        assert "synthesis" in row
        assert (row["synthesis"] or {}).get("schema") == "trade_event_synthesis_v1"
        assert "policy_snapshot" in row["synthesis"]
        assert "execution_snapshot" in row["synthesis"]


