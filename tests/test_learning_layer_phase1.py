"""Phase 1 learning layer — label specs + golden cases (no live DB required)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    ensure_execution_ledger_schema,
)
from modules.anna_training.learning_layer.label_specs import (
    WHIPSAW_LOOKAHEAD_BARS,
    beats_baseline_label,
    compute_whipsaw_flag,
    stopped_early_label,
    trade_success_label,
)
from modules.anna_training.learning_layer.schema import LEARNING_DATASET_SCHEMA_VERSION, schema_dict


def test_schema_version_constant() -> None:
    assert LEARNING_DATASET_SCHEMA_VERSION == "learning_dataset_baseline_v1"
    d = schema_dict()
    assert d["learning_dataset_schema_version"] == LEARNING_DATASET_SCHEMA_VERSION
    names = {c["name"] for c in d["columns"]}
    assert "trade_success" in names and "whipsaw_flag" in names


def test_trade_success_and_stopped_golden() -> None:
    assert trade_success_label(exit_reason="TAKE_PROFIT") is True
    assert trade_success_label(exit_reason="STOP_LOSS") is False
    assert stopped_early_label(exit_reason="STOP_LOSS") is True
    assert stopped_early_label(exit_reason="TAKE_PROFIT") is False


def test_beats_baseline_phase1_is_positive_pnl() -> None:
    assert beats_baseline_label(pnl_usd=1.0) is True
    assert beats_baseline_label(pnl_usd=-0.5) is False
    assert beats_baseline_label(pnl_usd=None) is False


def test_whipsaw_golden_long_revisits_entry() -> None:
    bars = [{"high": 100.5, "low": 99.0, "open": 99.5, "close": 100.0} for _ in range(WHIPSAW_LOOKAHEAD_BARS)]
    assert (
        compute_whipsaw_flag(
            side="long",
            entry_price=100.0,
            exit_reason="STOP_LOSS",
            bars_after_exit=bars,
        )
        is True
    )
    bars_low = [{"high": 99.0, "low": 98.0, "open": 98.5, "close": 98.5} for _ in range(3)]
    assert (
        compute_whipsaw_flag(
            side="long",
            entry_price=100.0,
            exit_reason="STOP_LOSS",
            bars_after_exit=bars_low,
        )
        is False
    )


def test_whipsaw_false_if_not_stopped() -> None:
    bars = [{"high": 200.0, "low": 199.0, "open": 199.5, "close": 199.8}]
    assert (
        compute_whipsaw_flag(
            side="long",
            entry_price=100.0,
            exit_reason="TAKE_PROFIT",
            bars_after_exit=bars,
        )
        is False
    )


def test_phase1_dataset_build_smoke(tmp_path: Path) -> None:
    """Minimal ledger + market DB with one lifecycle row."""
    ledger = tmp_path / "execution_ledger.db"
    market = tmp_path / "market_data.db"
    conn_l = sqlite3.connect(ledger)
    conn_m = sqlite3.connect(market)
    try:
        root = Path(__file__).resolve().parents[1]
        ensure_execution_ledger_schema(conn_l, root=root)
        conn_m.executescript(
            """
            CREATE TABLE market_bars_5m (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              canonical_symbol TEXT NOT NULL,
              tick_symbol TEXT NOT NULL,
              timeframe TEXT NOT NULL DEFAULT '5m',
              candle_open_utc TEXT NOT NULL,
              candle_close_utc TEXT NOT NULL,
              market_event_id TEXT NOT NULL UNIQUE,
              open REAL, high REAL, low REAL, close REAL,
              tick_count INTEGER NOT NULL DEFAULT 0,
              volume_base REAL,
              price_source TEXT NOT NULL DEFAULT 'pyth_primary',
              bar_schema_version TEXT NOT NULL DEFAULT 'canonical_bar_v1',
              computed_at TEXT NOT NULL
            );
            """
        )
        mid_e = "evt_entry_test"
        mid_x = "evt_exit_test"
        conn_m.execute(
            """
            INSERT INTO market_bars_5m (
              canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
              market_event_id, open, high, low, close, tick_count, computed_at
            ) VALUES (?, ?, '5m', '2026-01-01T00:00:00Z', '2026-01-01T00:05:00Z', ?, 100, 101, 99, 100.5, 1, '2026-01-01T00:05:01Z')
            """,
            ("SOL-PERP", "SOL-PERP", mid_e),
        )
        conn_m.execute(
            """
            INSERT INTO market_bars_5m (
              canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
              market_event_id, open, high, low, close, tick_count, computed_at
            ) VALUES (?, ?, '5m', '2026-01-01T00:05:00Z', '2026-01-01T00:10:00Z', ?, 100.5, 102, 100, 101.5, 1, '2026-01-01T00:10:01Z')
            """,
            ("SOL-PERP", "SOL-PERP", mid_x),
        )
        conn_m.execute(
            """
            INSERT INTO market_bars_5m (
              canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc,
              market_event_id, open, high, low, close, tick_count, computed_at
            ) VALUES (?, ?, '5m', '2026-01-01T00:10:00Z', '2026-01-01T00:15:00Z', ?, 101.5, 103, 101, 102.5, 1, '2026-01-01T00:15:01Z')
            """,
            ("SOL-PERP", "SOL-PERP", "evt_after_1"),
        )
        conn_m.commit()

        ctx = {"entry_market_event_id": mid_e, "lifecycle": "exit"}
        conn_l.execute(
            """
            INSERT INTO policy_evaluations (
              market_event_id, lane, strategy_id, signal_mode, tick_mode,
              trade, side, reason_code, features_json, pnl_usd, evaluated_at_utc, schema_version
            ) VALUES (?, 'baseline', 'baseline', 'sean_jupiter_v1', 'paper',
              1, 'long', 'jupiter_2_long_signal', ?, NULL, '2026-01-01T00:00:01Z', 'policy_evaluation_v1')
            """,
            (mid_e, json.dumps({"atr_ratio": 1.4, "position_size_hint": {"notional_usd": 1000.0}})),
        )
        conn_l.execute(
            """
            INSERT INTO execution_trades (
              trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
              side, entry_price, exit_price, size, exit_reason, pnl_usd,
              context_snapshot_json, notes, schema_version, created_at_utc
            ) VALUES (?, ?, 'baseline', 'paper', ?, 'SOL-PERP', '5m',
              'long', 100.5, 99.0, 10.0, 'STOP_LOSS', -15.0, ?, '', 'execution_trade_v1', '2026-01-01T00:10:02Z')
            """,
            (
                "tr_test_1",
                RESERVED_STRATEGY_BASELINE,
                mid_x,
                json.dumps(ctx),
            ),
        )
        conn_l.commit()
    finally:
        conn_l.close()
        conn_m.close()

    from modules.anna_training.learning_layer.dataset_builder import build_phase1_dataset
    from modules.anna_training.learning_layer.walk_forward_report import generate_walk_forward_report, report_to_dict

    rows, inv = build_phase1_dataset(ledger_db_path=ledger, market_db_path=market)
    assert inv.get("error") is None
    assert len(rows) == 1
    r0 = rows[0]
    assert r0["trade_id"] == "tr_test_1"
    assert r0["stopped_early"] is True
    assert r0["trade_success"] is False
    assert r0["beats_baseline"] is False
    assert r0["exit_reason"] == "STOP_LOSS"
    rep = generate_walk_forward_report(ledger_db_path=ledger, market_db_path=market)
    d = report_to_dict(rep)
    assert d["total_rows"] == 1
    assert "label_counts" in d
