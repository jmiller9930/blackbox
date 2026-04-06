"""Smoke tests for dashboard bundle (trade chain + aggregate)."""

from __future__ import annotations

from modules.anna_training.dashboard_bundle import (
    _pair_vs_baseline_for_cells,
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


