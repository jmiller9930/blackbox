"""Tests for Phase 5.1 gate composition including optional Jupiter (tertiary) leg."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from datetime import datetime, timezone

from market_data.gates import GateState, evaluate_gates  # noqa: E402


def _fresh_ts(wall: datetime) -> str:
    return wall.replace(microsecond=0).isoformat()


def test_two_leg_only_tertiary_skipped_in_details():
    wall = datetime.now(timezone.utc)
    ts = _fresh_ts(wall)
    gr = evaluate_gates(
        primary_observed_at=ts,
        comparator_observed_at=ts,
        primary_price=100.0,
        comparator_price=100.0,
        wall_now=wall,
    )
    assert gr.state == GateState.OK
    assert gr.details.get("tertiary") == {"skipped": True}
    assert gr.details.get("gate_mode") == "pyth_vs_coinbase"
    assert len(gr.reason.split(";")) == 3


def test_jupiter_king_blocks_when_pyth_not_tracking_king():
    wall = datetime.now(timezone.utc)
    ts = _fresh_ts(wall)
    gr = evaluate_gates(
        primary_observed_at=ts,
        comparator_observed_at=ts,
        primary_price=100.0,
        comparator_price=100.0,
        tertiary_observed_at=ts,
        tertiary_price=110.0,
        wall_now=wall,
    )
    assert gr.state == GateState.BLOCKED
    assert gr.details.get("gate_mode") == "jupiter_king"
    assert "divergence_exceeded" in gr.reason


def test_jupiter_king_ok_when_pyth_and_coinbase_support_king():
    wall = datetime.now(timezone.utc)
    ts = _fresh_ts(wall)
    gr = evaluate_gates(
        primary_observed_at=ts,
        comparator_observed_at=ts,
        primary_price=100.0,
        comparator_price=100.0,
        tertiary_observed_at=ts,
        tertiary_price=100.25,
        wall_now=wall,
    )
    assert gr.state == GateState.OK
    assert gr.details.get("gate_mode") == "jupiter_king"


def test_jupiter_king_blocks_when_coinbase_does_not_support_king():
    wall = datetime.now(timezone.utc)
    ts = _fresh_ts(wall)
    gr = evaluate_gates(
        primary_observed_at=ts,
        comparator_observed_at=ts,
        primary_price=100.01,
        comparator_price=106.0,
        tertiary_observed_at=ts,
        tertiary_price=100.0,
        wall_now=wall,
    )
    assert gr.state == GateState.BLOCKED
    assert gr.details.get("gate_mode") == "jupiter_king"
    assert "divergence_coinbase_supports_jupiter_king" in gr.details
