"""Regression: bundle must not drop JUPv3 entry policy from build_jupiter_policy_snapshot."""

from __future__ import annotations

from modules.anna_training.dashboard_bundle import _merge_jupiter_entry_policy_from_policy_snapshot


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
