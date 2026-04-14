"""DV-ARCH-023-A/B: policy activation log + evaluation/trade lineage."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_resolve_matches_kv_when_activation_empty(tmp_path: Path) -> None:
    from modules.anna_training.execution_ledger import (
        BASELINE_POLICY_SLOT_JUP_V2,
        ensure_execution_ledger_schema,
        get_baseline_jupiter_policy_slot,
        resolve_baseline_jupiter_policy_for_execution,
        set_baseline_jupiter_policy_slot,
    )

    db = tmp_path / "l.db"
    conn = sqlite3.connect(db)
    ensure_execution_ledger_schema(conn)
    assert resolve_baseline_jupiter_policy_for_execution(conn) == BASELINE_POLICY_SLOT_JUP_V2
    set_baseline_jupiter_policy_slot(conn, "jup_v3")
    conn.commit()
    assert get_baseline_jupiter_policy_slot(conn) == "jup_v3"
    assert resolve_baseline_jupiter_policy_for_execution(conn) == "jup_v2"
    conn.close()


def test_pending_superseded_on_new_set(tmp_path: Path) -> None:
    from modules.anna_training.execution_ledger import (
        POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
        ensure_execution_ledger_schema,
        set_baseline_jupiter_policy_slot,
    )

    db = tmp_path / "l2.db"
    conn = sqlite3.connect(db)
    ensure_execution_ledger_schema(conn)
    set_baseline_jupiter_policy_slot(conn, "jup_v3", assigned_by="t1")
    set_baseline_jupiter_policy_slot(conn, "jup_v4", assigned_by="t2")
    conn.commit()
    n_pend = conn.execute(
        "SELECT COUNT(*) FROM policy_activation_log WHERE activation_state = 'pending'"
    ).fetchone()[0]
    assert int(n_pend) == 1
    row = conn.execute(
        "SELECT policy_version FROM policy_activation_log WHERE activation_state = 'pending'",
    ).fetchone()
    assert row and "jupiter_4" in str(row[0])
    n_sup = conn.execute(
        "SELECT COUNT(*) FROM policy_activation_log WHERE activation_state = 'superseded'"
    ).fetchone()[0]
    assert int(n_sup) == 1
    conn.close()


def test_activation_at_next_bar_boundary(tmp_path: Path) -> None:
    from modules.anna_training.execution_ledger import (
        apply_baseline_jupiter_policy_activation_at_bar,
        ensure_execution_ledger_schema,
        resolve_baseline_jupiter_policy_for_execution,
        set_baseline_jupiter_policy_slot,
    )

    db = tmp_path / "l3.db"
    conn = sqlite3.connect(db)
    ensure_execution_ledger_schema(conn)
    set_baseline_jupiter_policy_slot(conn, "jup_v3")
    conn.commit()
    assert resolve_baseline_jupiter_policy_for_execution(conn) != "jup_v3"
    apply_baseline_jupiter_policy_activation_at_bar(
        conn,
        market_event_id="SOL-PERP_5m_2099-01-01T00:05:00Z",
        candle_open_utc="2099-01-01T00:05:00Z",
    )
    conn.commit()
    assert resolve_baseline_jupiter_policy_for_execution(conn) == "jup_v3"
    st = conn.execute(
        "SELECT activation_state FROM policy_activation_log WHERE slot = ? ORDER BY id DESC LIMIT 1",
        ("baseline_jupiter",),
    ).fetchone()
    assert st and st[0] == "active"
    conn.close()


def test_upsert_policy_evaluation_lineage_columns(tmp_path: Path) -> None:
    from modules.anna_training.execution_ledger import (
        POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
        ensure_execution_ledger_schema,
        upsert_policy_evaluation,
    )

    db = tmp_path / "l4.db"
    conn = sqlite3.connect(db)
    ensure_execution_ledger_schema(conn)
    mid = "X_5m_2026-01-01T00:00:00Z"
    upsert_policy_evaluation(
        market_event_id=mid,
        signal_mode="sean_jupiter_v1",
        tick_mode="paper",
        trade=False,
        reason_code="x",
        features={"a": 1},
        side="flat",
        policy_id="jupiter_2_sean_perps_v1",
        policy_version="jupiter_2",
        slot=POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
        db_path=db,
    )
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT policy_id, policy_version, slot FROM policy_evaluations WHERE market_event_id = ?",
        (mid,),
    ).fetchone()
    conn.close()
    assert row == ("jupiter_2_sean_perps_v1", "jupiter_2", POLICY_ACTIVATION_SLOT_BASELINE_JUPITER)
