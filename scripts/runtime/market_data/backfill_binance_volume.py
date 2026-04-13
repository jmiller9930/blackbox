#!/usr/bin/env python3
"""
Backfill ``market_bars_5m.volume_base`` from Binance 5m kline **quote volume** for rows missing it.

Use when ingest could not write volume earlier (TLS failure, downtime) or before Binance enrichment
existed. Does not change OHLC (Pyth); only sets ``volume_base``.

  cd /repo && PYTHONPATH=scripts/runtime python3 scripts/runtime/market_data/backfill_binance_volume.py

Environment: same as ``binance_kline_volume`` (``BLACKBOX_MARKET_DATA_PATH``, ``BLACKBOX_BINANCE_KLINE_SYMBOL``).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# scripts/runtime on path (…/scripts/runtime/market_data/this.py → parents[1] == runtime)
_RUNTIME = Path(__file__).resolve().parents[1]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from _paths import default_market_data_path  # noqa: E402
from market_data.binance_kline_volume import (  # noqa: E402
    binance_spot_symbol_for_canonical,
    fetch_binance_quote_volume_5m,
)
from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP  # noqa: E402


def _parse_open_utc(s: str) -> datetime | None:
    raw = (s or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill volume_base from Binance klines for SOL-PERP 5m bars.")
    ap.add_argument(
        "--db",
        type=Path,
        default=None,
        help="market_data SQLite (default: BLACKBOX_MARKET_DATA_PATH or data/sqlite/market_data.db)",
    )
    ap.add_argument("--limit", type=int, default=500, help="Max rows to attempt (newest first).")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be updated without writing.",
    )
    args = ap.parse_args()

    db_path = args.db or default_market_data_path()
    if not db_path.is_file():
        print(f"backfill_binance_volume: no database at {db_path}", file=sys.stderr)
        return 1

    sym = binance_spot_symbol_for_canonical(CANONICAL_INSTRUMENT_SOL_PERP)
    if not sym:
        print("backfill_binance_volume: no Binance symbol mapping for SOL-PERP", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT market_event_id, candle_open_utc, volume_base
            FROM market_bars_5m
            WHERE canonical_symbol = ? AND timeframe = '5m'
              AND (volume_base IS NULL OR volume_base = 0)
            ORDER BY candle_open_utc DESC
            LIMIT ?
            """,
            (CANONICAL_INSTRUMENT_SOL_PERP, int(args.limit)),
        ).fetchall()
    except sqlite3.OperationalError as e:
        print(f"backfill_binance_volume: query failed: {e}", file=sys.stderr)
        conn.close()
        return 1

    updated = 0
    failed = 0
    for meid, open_s, _vb in rows:
        dt = _parse_open_utc(str(open_s or ""))
        if dt is None:
            failed += 1
            continue
        qv = fetch_binance_quote_volume_5m(binance_symbol=sym, candle_open_utc=dt)
        if qv is None:
            print(f"skip {meid} (fetch failed or no matching kline)", file=sys.stderr)
            failed += 1
            continue
        if args.dry_run:
            print(f"would set {meid} volume_base={qv}")
            updated += 1
            continue
        conn.execute(
            "UPDATE market_bars_5m SET volume_base = ? WHERE market_event_id = ?",
            (qv, meid),
        )
        conn.commit()
        updated += 1
        print(f"updated {meid} volume_base={qv}")

    print(
        f"backfill_binance_volume: done rows_attempted={len(rows)} updated={updated} failed={failed} db={db_path}",
        file=sys.stderr,
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
