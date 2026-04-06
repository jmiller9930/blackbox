"""Learning proof bundle — memory attribution + vs-baseline aggregates."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.anna_training.learning_proof import (
    build_learning_proof_bundle,
    compute_learning_proof_attachment,
)


def test_compute_learning_proof_ablation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_LEARNING_PROOF_MEMORY_OFF", "1")
    bar = {
        "canonical_symbol": "SOL-PERP",
        "timeframe": "5m",
        "open": 100.0,
        "close": 101.0,
        "market_event_id": "e1",
    }
    lp = compute_learning_proof_attachment(
        strategy_id="s_test",
        market_event_id="e1",
        bar=bar,
        mode="paper",
    )
    assert lp["memory_ablation_off"] is True
    assert lp["memory_used"] is False
    assert lp["retrieved_memory_ids"] == []


def test_build_learning_proof_bundle_empty_trade_chain() -> None:
    tc = {"schema": "blackbox_trade_chain_v1", "rows": [], "event_axis": []}
    out = build_learning_proof_bundle(trade_chain=tc)
    assert out["schema"] == "learning_proof_bundle_v1"
    assert out["aggregate"]["learning_proof_status"] == "insufficient_data"


def test_trace_roundtrip_includes_learning_proof_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANNA_LEARNING_PROOF_MEMORY_OFF", "1")
    db = tmp_path / "el.db"
    monkeypatch.setenv("BLACKBOX_EXECUTION_LEDGER_PATH", str(db))
    from modules.anna_training.decision_trace import persist_parallel_anna_paper_trade_with_trace
    from modules.anna_training.execution_ledger import connect_ledger, ensure_execution_ledger_schema

    bar = {
        "id": 42,
        "canonical_symbol": "SOL-PERP",
        "timeframe": "5m",
        "candle_open_utc": "2026-04-01T19:55:00Z",
        "candle_close_utc": "2026-04-01T20:00:00Z",
        "market_event_id": "SOL-PERP_5m_2026-04-01T19:55:00Z",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
    }
    out = persist_parallel_anna_paper_trade_with_trace(
        market_event_id=bar["market_event_id"],
        strategy_id="s_lp_test_v1",
        bar=bar,
        trade_id="trade_lp_1",
        context_snapshot={},
        notes="test",
        db_path=db,
    )
    assert out.get("learning_proof") is not None
    conn = connect_ledger(db)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            "SELECT memory_used, retrieved_memory_ids_json, memory_ablation_off FROM decision_traces WHERE trace_id = ?",
            (out["trace_id"],),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 0
        assert row[2] == 1
    finally:
        conn.close()
