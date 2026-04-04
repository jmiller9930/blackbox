"""Operator dashboard — top-five selection rule (server-side)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.anna_training.execution_ledger import connect_ledger, ensure_execution_ledger_schema
from modules.anna_training.operator_dashboard import (
    TOP_FIVE_RULE_DESCRIPTION,
    select_top_five_anna_strategy_ids,
)


def test_top_five_rule_description_mentions_lifecycle_and_pnl() -> None:
    assert "lifecycle" in TOP_FIVE_RULE_DESCRIPTION.lower()
    assert "P&L" in TOP_FIVE_RULE_DESCRIPTION or "P\u0026L" in TOP_FIVE_RULE_DESCRIPTION


def test_select_top_five_prefers_higher_lifecycle(tmp_path: Path) -> None:
    db = tmp_path / "el.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    conn.execute(
        """
        INSERT INTO strategy_registry (
          strategy_id, title, description, registered_at_utc, source,
          lifecycle_state, parent_strategy_id, qel_updated_at_utc
        ) VALUES
          ('z_low', 'z', 'd', '2026-01-01T00:00:00Z', 'catalog', 'experiment', NULL, NULL),
          ('a_high', 'a', 'd', '2026-01-01T00:00:00Z', 'catalog', 'candidate', NULL, NULL)
        """
    )
    conn.commit()
    conn.close()

    top, _ = select_top_five_anna_strategy_ids(db_path=db)
    assert top[0] == "a_high"
    assert "z_low" in top


def test_select_top_five_tiebreak_pnl(tmp_path: Path) -> None:
    db = tmp_path / "el2.db"
    conn = connect_ledger(db)
    ensure_execution_ledger_schema(conn)
    conn.execute(
        """
        INSERT INTO strategy_registry (
          strategy_id, title, description, registered_at_utc, source,
          lifecycle_state, parent_strategy_id, qel_updated_at_utc
        ) VALUES
          ('s_b', 'b', 'd', '2026-01-01T00:00:00Z', 'catalog', 'experiment', NULL, NULL),
          ('s_a', 'a', 'd', '2026-01-01T00:00:00Z', 'catalog', 'experiment', NULL, NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO execution_trades (
          trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
          side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
          pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
        ) VALUES
          ('t1', 's_a', 'anna', 'paper', 'MID', 'SOL', '5m', 'long',
           '2026-01-01', 100, 1, '2026-01-01', 101, 'x', 10.0, NULL, NULL, NULL, 'execution_trade_v1', '2026-01-01T00:00:00Z'),
          ('t2', 's_b', 'anna', 'paper', 'MID', 'SOL', '5m', 'long',
           '2026-01-01', 100, 1, '2026-01-01', 101, 'x', 1.0, NULL, NULL, NULL, 'execution_trade_v1', '2026-01-01T00:00:00Z')
        """
    )
    conn.commit()
    conn.close()

    top, _ = select_top_five_anna_strategy_ids(db_path=db)
    assert top[0] == "s_a"
