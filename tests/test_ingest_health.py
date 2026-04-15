"""Ingest watchdog: tick age + canonical bar advancement vs thresholds."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.store import connect_market_db, ensure_market_schema  # noqa: E402
from _paths import repo_root  # noqa: E402


def _seed_minimal_schema(conn: sqlite3.Connection) -> None:
    ensure_market_schema(conn, repo_root())


def test_ingest_health_operational_when_fresh_tick_and_current_bar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.anna_training.ingest_health import compute_ingest_health

    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    _seed_minimal_schema(conn)
    now = datetime(2035, 1, 1, 12, 17, 0, tzinfo=timezone.utc)
    ins = now.replace(second=0).isoformat()
    conn.execute(
        """
        INSERT INTO market_ticks (
          symbol, inserted_at, primary_source, primary_price, primary_observed_at,
          primary_publish_time, primary_raw_json, comparator_source, comparator_price,
          comparator_observed_at, gate_state, gate_reason
        ) VALUES (?, ?, 'pyth_hermes_sse', 100.0, ?, NULL, NULL, 'none', NULL, NULL, 'ok', 'ok')
        """,
        ("SOL-USD", ins, ins),
    )
    # last closed open at 12:10 when now is 12:17
    from market_data.canonical_time import (
        candle_close_utc_exclusive,
        format_candle_open_iso_z,
        last_closed_candle_open_utc,
    )

    exp = last_closed_candle_open_utc(now)
    co = format_candle_open_iso_z(exp)
    cc = format_candle_open_iso_z(candle_close_utc_exclusive(exp))
    mei = f"SOL-PERP_5m_{co}"
    conn.execute(
        """
        INSERT INTO market_bars_5m (
          canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc, market_event_id,
          open, high, low, close, tick_count, volume_base, price_source, bar_schema_version, computed_at
        ) VALUES ('SOL-PERP', 'SOL-USD', '5m', ?, ?, ?, 100, 101, 99, 100.5, 1, 0, 'pyth_primary', 'canonical_bar_v1', ?)
        """,
        (co, cc, mei, ins),
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("INGEST_HEALTH_TICK_MAX_AGE_SEC", "180")
    monkeypatch.setenv("INGEST_HEALTH_BAR_MAX_LAG_SEC", "180")

    r = compute_ingest_health(market_db_path=db, now=now)
    assert r["healthy"] is True
    assert r["state"] == "operational"
    assert r["operator_alert_code"] == "NONE"


def test_ingest_health_tick_stalled_when_no_recent_hermes_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.anna_training.ingest_health import compute_ingest_health

    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    _seed_minimal_schema(conn)
    stale = "2035-01-01T11:00:00+00:00"
    conn.execute(
        """
        INSERT INTO market_ticks (
          symbol, inserted_at, primary_source, primary_price, primary_observed_at,
          primary_publish_time, primary_raw_json, comparator_source, comparator_price,
          comparator_observed_at, gate_state, gate_reason
        ) VALUES (?, ?, 'pyth_hermes_sse', 100.0, ?, NULL, NULL, 'none', NULL, NULL, 'ok', 'ok')
        """,
        ("SOL-USD", stale, stale),
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("INGEST_HEALTH_TICK_MAX_AGE_SEC", "120")
    now = datetime(2035, 1, 1, 12, 10, 0, tzinfo=timezone.utc)
    r = compute_ingest_health(market_db_path=db, now=now)
    assert r["healthy"] is False
    assert r["state"] == "ingest_down"
    assert r["operator_alert_code"] == "INGEST_DOWN"
    assert r["tick"]["stalled"] is True


def test_ingest_health_bar_stalled_when_max_open_behind_expected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate ingest running (fresh tick) but rollup stuck — bar side fires."""
    from modules.anna_training.ingest_health import compute_ingest_health

    db = tmp_path / "m.db"
    conn = connect_market_db(db)
    _seed_minimal_schema(conn)
    now = datetime(2035, 1, 1, 12, 22, 0, tzinfo=timezone.utc)
    ins = now.isoformat()
    conn.execute(
        """
        INSERT INTO market_ticks (
          symbol, inserted_at, primary_source, primary_price, primary_observed_at,
          primary_publish_time, primary_raw_json, comparator_source, comparator_price,
          comparator_observed_at, gate_state, gate_reason
        ) VALUES (?, ?, 'pyth_hermes_sse', 100.0, ?, NULL, NULL, 'none', NULL, NULL, 'ok', 'ok')
        """,
        ("SOL-USD", ins, ins),
    )
    # Only an old bar row (well behind expected last closed)
    conn.execute(
        """
        INSERT INTO market_bars_5m (
          canonical_symbol, tick_symbol, timeframe, candle_open_utc, candle_close_utc, market_event_id,
          open, high, low, close, tick_count, volume_base, price_source, bar_schema_version, computed_at
        ) VALUES (
          'SOL-PERP', 'SOL-USD', '5m', '2035-01-01T11:30:00Z', '2035-01-01T11:35:00Z',
          'SOL-PERP_5m_2035-01-01T11:30:00Z',
          100, 101, 99, 100.5, 1, 0, 'pyth_primary', 'canonical_bar_v1', '2035-01-01T11:35:01Z'
        )
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("INGEST_HEALTH_TICK_MAX_AGE_SEC", "300")
    monkeypatch.setenv("INGEST_HEALTH_BAR_MAX_LAG_SEC", "60")
    r = compute_ingest_health(market_db_path=db, now=now)
    assert r["healthy"] is False
    assert r["bars"]["stalled"] is True
    assert r["operator_alert_code"] == "BARS_STALLED"
