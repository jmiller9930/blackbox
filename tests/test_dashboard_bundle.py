"""Smoke tests for dashboard bundle (trade chain + aggregate)."""

from __future__ import annotations

from modules.anna_training.dashboard_bundle import build_dashboard_bundle, build_trade_chain_payload


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
    assert "market_clock" in tc
    assert tc["rows"][0].get("chain_kind") == "baseline"
    assert tc["rows"][0].get("row_tier") == "primary"
    assert (tc.get("recency") or {}).get("axis_order") == "oldest_left_newest_right"


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
