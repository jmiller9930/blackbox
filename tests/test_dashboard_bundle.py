"""Smoke tests for dashboard bundle (trade chain + aggregate)."""

from __future__ import annotations

from modules.anna_training.dashboard_bundle import build_dashboard_bundle, build_trade_chain_payload


def test_build_trade_chain_payload_schema() -> None:
    tc = build_trade_chain_payload(max_events=8)
    assert tc.get("schema") == "blackbox_trade_chain_v1"
    assert "event_axis" in tc
    assert "rows" in tc
    assert isinstance(tc["rows"], list)


def test_build_dashboard_bundle_schema() -> None:
    b = build_dashboard_bundle(max_events=8)
    assert b.get("schema") == "blackbox_dashboard_bundle_v1"
    assert "trade_chain" in b
    assert "sequential" in b
    assert "operational_boundary" in b
    assert "learning_summary" in b
