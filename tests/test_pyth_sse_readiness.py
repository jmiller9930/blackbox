"""readiness.check_pyth_sse_tape — SQLite SSE tick age (no Hermes)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.store import connect_market_db, ensure_market_schema, insert_tick  # noqa: E402
from _paths import repo_root  # noqa: E402


def test_check_pyth_sse_tape_fresh(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BLACKBOX_MARKET_DATA_PATH", str(tmp_path / "m.db"))
    from modules.anna_training.readiness import check_pyth_sse_tape

    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    insert_tick(
        conn,
        symbol="SOL-USD",
        inserted_at="2099-01-01T00:00:00+00:00",
        primary_source="pyth_hermes_sse",
        primary_price=100.0,
        primary_observed_at="2099-01-01T00:00:00+00:00",
        primary_publish_time=1,
        primary_raw={"x": 1},
        comparator_source="none",
        comparator_price=None,
        comparator_observed_at=None,
        comparator_raw=None,
        gate_state="ok",
        gate_reason="pyth_sse_stream_ingest",
    )
    conn.close()

    r = check_pyth_sse_tape(repo_root=tmp_path)
    assert r.get("ok") is True
    assert r.get("sse_tick_count", 0) >= 1


def test_check_pyth_sse_tape_stale(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BLACKBOX_MARKET_DATA_PATH", str(tmp_path / "m.db"))
    from modules.anna_training.readiness import check_pyth_sse_tape

    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    ensure_market_schema(conn, repo_root())
    insert_tick(
        conn,
        symbol="SOL-USD",
        inserted_at="2020-01-01T00:00:00+00:00",
        primary_source="pyth_hermes_sse",
        primary_price=1.0,
        primary_observed_at="2020-01-01T00:00:00+00:00",
        primary_publish_time=1,
        primary_raw={},
        comparator_source="none",
        comparator_price=None,
        comparator_observed_at=None,
        comparator_raw=None,
        gate_state="ok",
        gate_reason="pyth_sse_stream_ingest",
    )
    conn.close()

    r = check_pyth_sse_tape(repo_root=tmp_path)
    assert r.get("ok") is False
    assert r.get("reason") == "sse_tape_stale"
