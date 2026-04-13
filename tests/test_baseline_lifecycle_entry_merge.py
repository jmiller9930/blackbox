"""Regression: bundle must not drop JUPv3 entry policy from build_jupiter_policy_snapshot."""

from __future__ import annotations

from modules.anna_training.dashboard_bundle import (
    _merge_jupiter_entry_policy_from_policy_snapshot,
    _v3_entry_narrative_and_gates_from_open_position,
)
from modules.anna_training.jupiter_2_baseline_lifecycle import BaselineOpenPosition


def test_v3_entry_coalesce_from_signal_features_when_snapshot_fields_empty() -> None:
    """If dedicated entry_* snapshots were never written, recover from signal_features_snapshot."""
    pos = BaselineOpenPosition(
        trade_id="t1",
        side="long",
        entry_price=1.0,
        entry_market_event_id="SOL-PERP_5m_2026-01-01T00:00:00Z",
        entry_candle_open_utc="",
        atr_entry=0.1,
        stop_loss=0.9,
        take_profit=1.1,
        initial_stop_loss=0.9,
        initial_take_profit=1.1,
        breakeven_applied=False,
        size=1.0,
        last_processed_market_event_id="SOL-PERP_5m_2026-01-01T00:00:00Z",
        entry_policy_narrative_snapshot="",
        entry_jupiter_v3_gates_snapshot=None,
        signal_features_snapshot={
            "jupiter_policy_narrative": "from features",
            "jupiter_v3_gates": {"schema": "jupiter_v3_gates_v1", "long": {"all_ok": True}},
        },
    )
    n, g = _v3_entry_narrative_and_gates_from_open_position(pos)
    assert n == "from features"
    assert isinstance(g, dict) and g.get("long", {}).get("all_ok") is True


def test_merge_fills_missing_entry_gates_and_narrative_from_policy_snapshot() -> None:
    dash = {
        "position_open": True,
        "trade_id": "bl_t1",
        "entry_market_event_id": "SOL-PERP_5m_2026-01-01T00:00:00Z",
        "entry_jupiter_tile_narrative": None,
        "entry_jupiter_v3_gates": None,
    }
    pol = {
        "position_open": True,
        "trade_id": "bl_t1",
        "entry_market_event_id": "SOL-PERP_5m_2026-01-01T00:00:00Z",
        "entry_jupiter_tile_narrative": "narr",
        "entry_jupiter_v3_gates": {"schema": "jupiter_v3_gates_v1", "rows": []},
    }
    _merge_jupiter_entry_policy_from_policy_snapshot(dash, pol)
    assert dash["entry_jupiter_tile_narrative"] == "narr"
    assert isinstance(dash["entry_jupiter_v3_gates"], dict)


def test_merge_does_not_overwrite_existing_entry_gates_from_policy_snapshot() -> None:
    """Ledger-backed entry gates are authoritative; policy snapshot must not replace them."""
    dash = {
        "position_open": True,
        "trade_id": "bl_t1",
        "entry_market_event_id": "SOL-PERP_5m_2026-01-01T00:00:00Z",
        "entry_jupiter_v3_gates": {
            "schema": "jupiter_v3_gates_v1",
            "long": {"all_ok": False},
        },
    }
    pol = {
        "position_open": True,
        "trade_id": "bl_t1",
        "entry_market_event_id": "SOL-PERP_5m_2026-01-01T00:00:00Z",
        "entry_jupiter_v3_gates": {
            "schema": "jupiter_v3_gates_v1",
            "long": {"all_ok": True},
        },
    }
    _merge_jupiter_entry_policy_from_policy_snapshot(dash, pol)
    assert dash["entry_jupiter_v3_gates"]["long"]["all_ok"] is False


def test_merge_copies_recomputed_audit_from_policy_snapshot() -> None:
    dash = {
        "position_open": True,
        "trade_id": "bl_t1",
        "entry_market_event_id": "SOL-PERP_5m_2026-01-01T00:00:00Z",
        "entry_jupiter_v3_gates": {"schema": "jupiter_v3_gates_v1", "rows": []},
    }
    pol = {
        "position_open": True,
        "trade_id": "bl_t1",
        "entry_market_event_id": "SOL-PERP_5m_2026-01-01T00:00:00Z",
        "jupiter_v3_gates_recomputed_audit": {"schema": "jupiter_v3_gates_v1", "long": {"all_ok": False}},
        "jupiter_v3_gates_recomputed_audit_scope_note": "Current bar evaluation (not entry)",
    }
    _merge_jupiter_entry_policy_from_policy_snapshot(dash, pol)
    assert dash["jupiter_v3_gates_recomputed_audit"]["long"]["all_ok"] is False
    assert "not entry" in dash["jupiter_v3_gates_recomputed_audit_scope_note"]


def test_merge_skips_when_trade_id_differs() -> None:
    dash = {
        "position_open": True,
        "trade_id": "a",
        "entry_market_event_id": "SOL-PERP_5m_2026-01-01T00:00:00Z",
        "entry_jupiter_v3_gates": None,
    }
    pol = {
        "position_open": True,
        "trade_id": "b",
        "entry_jupiter_v3_gates": {"schema": "jupiter_v3_gates_v1"},
    }
    _merge_jupiter_entry_policy_from_policy_snapshot(dash, pol)
    assert dash["entry_jupiter_v3_gates"] is None
