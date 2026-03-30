"""Phase 5.3e — guardrailed self-directed paper/backtest experiments."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.guardrailed_experiment import (
    GUARDRAILED_EXPERIMENT_VERSION,
    run_guardrailed_paper_experiment,
)
from market_data.participant_scope import ParticipantScope
from market_data.store import connect_market_db, ensure_market_schema, insert_tick
from _paths import repo_root


def _scope(tier: str = "tier_2") -> ParticipantScope:
    return ParticipantScope(
        participant_id="sean",
        participant_type="human",
        account_id="acct_001",
        wallet_context="wallet_main",
        risk_tier=tier,
        interaction_path="cli",
    )


def _seed_ticks(db: Path, *, n: int = 3) -> None:
    root = repo_root()
    conn = connect_market_db(db)
    ensure_market_schema(conn, root)
    base = "2026-03-26T12:00:00+00:00"
    for i in range(n):
        insert_tick(
            conn,
            symbol="SOL-USD",
            inserted_at=f"2026-03-26T12:0{i}:00+00:00",
            primary_source="pyth_hermes",
            primary_price=100.0 + i * 0.01,
            primary_observed_at=f"2026-03-26T12:0{i}:00+00:00",
            primary_publish_time=i,
            primary_raw={"i": i},
            comparator_source="coinbase",
            comparator_price=100.05 + i * 0.01,
            comparator_observed_at=f"2026-03-26T12:0{i}:00+00:00",
            comparator_raw={"i": i},
            gate_state="ok",
            gate_reason="ok",
        )
    conn.close()


def test_version_constant():
    assert GUARDRAILED_EXPERIMENT_VERSION == "guardrailed_experiment_v1"


def test_guardrailed_experiment_happy_path(tmp_path: Path):
    db = tmp_path / "m.db"
    _seed_ticks(db, n=5)
    run = run_guardrailed_paper_experiment(
        _scope("tier_2"),
        "SOL-USD",
        experiment_id="test_exp_1",
        max_ticks=50,
        db_path=db,
    )
    assert run.error is None
    assert run.tier_unchanged_assertion is True
    assert run.simulation.sample_count == 5
    assert run.evaluation is not None
    assert run.gate is not None
    assert run.selection is not None
    assert run.selection.selected_risk_tier == "tier_2"
    assert run.original_risk_tier == "tier_2"


def test_guardrailed_experiment_empty_db(tmp_path: Path):
    db = tmp_path / "empty.db"
    root = repo_root()
    conn = connect_market_db(db)
    ensure_market_schema(conn, root)
    conn.close()
    run = run_guardrailed_paper_experiment(
        _scope(),
        "SOL-USD",
        experiment_id="empty",
        max_ticks=10,
        db_path=db,
    )
    assert run.simulation.error is not None or run.simulation.sample_count == 0
    assert run.evaluation is None


def test_guardrailed_to_dict_roundtrip(tmp_path: Path):
    db = tmp_path / "m.db"
    _seed_ticks(db, n=2)
    run = run_guardrailed_paper_experiment(
        _scope("tier_1"),
        "SOL-USD",
        experiment_id="dict",
        max_ticks=10,
        db_path=db,
    )
    d = run.to_dict()
    assert d["experiment_id"] == "dict"
    assert d["schema_version"] == "guardrailed_experiment_run_v1"
    assert d["simulation"]["sample_count"] >= 1
