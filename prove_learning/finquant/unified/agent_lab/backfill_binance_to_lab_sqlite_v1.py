#!/usr/bin/env python3
"""
FinQuant Agent Lab — Binance public klines → SQLite compatible with market_data_bridge.

Creates ``market_bars_5m`` rows using the same column names as ``market_data_bridge.fetch_5m_bars``:
canonical_symbol, candle_open_utc, open, high, low, close, tick_count, volume_base.

Usage (repo root) — live Binance:
  python finquant/unified/agent_lab/backfill_binance_to_lab_sqlite_v1.py \\
    --db data/sqlite/finquant_btcusdt_5m_lab.db \\
    --binance-symbol BTCUSDT \\
    --canonical-symbol BTC-USD \\
    --months 18

Offline demo (API blocked / HTTP 451):
  python ... --synthetic-demo --synthetic-bars 155520 --db data/sqlite/finquant_btc_demo.db
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import ssl
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
INTERVAL = "5m"
LIMIT = 1000
FIVE_MINUTES_MS = 5 * 60 * 1000

DDL = """
CREATE TABLE IF NOT EXISTS market_bars_5m (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_symbol TEXT NOT NULL,
  tick_symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL DEFAULT '5m',
  candle_open_utc TEXT NOT NULL,
  candle_close_utc TEXT NOT NULL,
  market_event_id TEXT NOT NULL UNIQUE,
  open REAL, high REAL, low REAL, close REAL,
  tick_count INTEGER NOT NULL DEFAULT 0,
  volume_base REAL,
  price_source TEXT NOT NULL DEFAULT 'binance_public_klines_v1',
  bar_schema_version TEXT NOT NULL DEFAULT 'canonical_bar_v1',
  computed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_m5m_canon_open ON market_bars_5m (canonical_symbol, candle_open_utc);
"""


def seed_synthetic_bars(
    *,
    db_path: str,
    canonical_symbol: str,
    tick_symbol: str,
    bar_count: int,
    seed: int,
) -> dict[str, object]:
    """
    Deterministic OHLC walk at 5m resolution for offline bridge tests when public APIs are blocked.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=5 * bar_count)

    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(DDL)
        conn.execute("DELETE FROM market_bars_5m WHERE canonical_symbol = ?", (canonical_symbol,))
        price = 50_000.0 + rng.uniform(-500, 500)
        t = start
        rows = []
        for i in range(bar_count):
            open_z = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            t_close = t + timedelta(minutes=5)
            close_z = t_close.strftime("%Y-%m-%dT%H:%M:%SZ")
            dt_sec = int(t.timestamp() * 1000)
            evt = f"synthetic_demo:{tick_symbol}:{dt_sec}"
            drift = rng.uniform(-0.0012, 0.0012) * price
            vol_shock = rng.uniform(0.5, 2.5)
            o = price
            c = max(1000.0, o + drift + rng.uniform(-80.0, 80.0))
            h = max(o, c) + rng.uniform(0, 120.0) * vol_shock
            low = min(o, c) - rng.uniform(0, 120.0) * vol_shock
            v_base = rng.uniform(10.0, 500.0) * vol_shock
            trades = rng.randint(50, 5000)
            rows.append(
                (
                    canonical_symbol,
                    tick_symbol,
                    "5m",
                    open_z,
                    close_z,
                    evt,
                    round(o, 2),
                    round(h, 2),
                    round(low, 2),
                    round(c, 2),
                    trades,
                    round(v_base, 4),
                    "synthetic_demo_v1",
                    "canonical_bar_v1",
                    close_z,
                )
            )
            price = c
            t = t_close

        conn.executemany(
            """
            INSERT INTO market_bars_5m (
              canonical_symbol, tick_symbol, timeframe,
              candle_open_utc, candle_close_utc, market_event_id,
              open, high, low, close, tick_count, volume_base,
              price_source, bar_schema_version, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM market_bars_5m WHERE canonical_symbol = ?",
            (canonical_symbol,),
        )
        (n,) = cur.fetchone()
    finally:
        conn.close()

    return {
        "db_path": str(path),
        "canonical_symbol": canonical_symbol,
        "mode": "synthetic_demo_v1",
        "bar_count": int(n),
        "seed": seed,
        "from_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to_utc": (start + timedelta(minutes=5 * bar_count)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def ms_to_z(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_klines(
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
    *,
    ssl_context: ssl.SSLContext | None,
) -> list[list]:
    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": LIMIT,
    }
    url = f"{BINANCE_KLINES_URL}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "finquant-agent-lab-backfill/1"})
    with urlopen(req, timeout=60, context=ssl_context) as response:
        return json.loads(response.read().decode("utf-8"))


def insert_batch(
    conn: sqlite3.Connection,
    *,
    canonical_symbol: str,
    binance_symbol: str,
    klines: list[list],
) -> int:
    rows = []
    for row in klines:
        open_ms = int(row[0])
        o, h, low, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
        vol_base = float(row[5])
        trades = int(row[8])
        close_ms = int(row[6])
        open_z = ms_to_z(open_ms)
        close_z = ms_to_z(close_ms)
        evt = f"binance:{binance_symbol}:{open_ms}"
        rows.append(
            (
                canonical_symbol,
                binance_symbol,
                "5m",
                open_z,
                close_z,
                evt,
                o,
                h,
                low,
                c,
                trades,
                vol_base,
                "binance_public_klines_v1",
                "canonical_bar_v1",
                close_z,
            )
        )
    conn.executemany(
        """
        INSERT OR IGNORE INTO market_bars_5m (
          canonical_symbol, tick_symbol, timeframe,
          candle_open_utc, candle_close_utc, market_event_id,
          open, high, low, close, tick_count, volume_base,
          price_source, bar_schema_version, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return conn.total_changes


def run_backfill(
    *,
    db_path: str,
    binance_symbol: str,
    canonical_symbol: str,
    months: int,
    sleep_s: float,
    insecure_ssl: bool,
) -> dict[str, object]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=int(months * 30))
    cursor_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    ssl_ctx: ssl.SSLContext | None
    if insecure_ssl:
        ssl_ctx = ssl._create_unverified_context()
    else:
        ssl_ctx = None

    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(DDL)
        total_batches = 0
        total_rows = 0
        while cursor_ms < end_ms:
            batch = fetch_klines(
                binance_symbol,
                cursor_ms,
                end_ms,
                ssl_context=ssl_ctx,
            )
            if not batch:
                break
            before = conn.total_changes
            insert_batch(
                conn,
                canonical_symbol=canonical_symbol,
                binance_symbol=binance_symbol,
                klines=batch,
            )
            inserted = conn.total_changes - before
            total_rows += inserted
            total_batches += 1
            last_open = int(batch[-1][0])
            next_ms = last_open + FIVE_MINUTES_MS
            if next_ms <= cursor_ms:
                raise RuntimeError("Cursor did not advance")
            cursor_ms = next_ms
            if total_batches % 20 == 0:
                print(f"[backfill] batches={total_batches} rows_ignored_or_inserted≈{total_rows} cursor={ms_to_z(cursor_ms)}")
            time.sleep(sleep_s)

        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM market_bars_5m WHERE canonical_symbol = ?",
            (canonical_symbol,),
        )
        (n,) = cur.fetchone()
    finally:
        conn.close()

    return {
        "db_path": str(path),
        "binance_symbol": binance_symbol,
        "canonical_symbol": canonical_symbol,
        "months_requested": months,
        "from_utc": ms_to_z(int(start.timestamp() * 1000)),
        "to_utc": ms_to_z(end_ms),
        "row_count": int(n),
        "batches": total_batches,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill Binance 5m klines into lab SQLite")
    p.add_argument("--db", required=True, help="SQLite path (parent dirs created)")
    p.add_argument("--binance-symbol", default="BTCUSDT", help="Binance pair, e.g. BTCUSDT")
    p.add_argument("--canonical-symbol", default="BTC-USD", help="Symbol passed to market_data_bridge")
    p.add_argument("--months", type=int, default=18, help="Approximate months (30d each)")
    p.add_argument("--sleep", type=float, default=0.2, help="Seconds between API batches")
    p.add_argument(
        "--insecure-ssl",
        action="store_true",
        help="Disable TLS certificate verification (use only if a proxy breaks cert chains)",
    )
    p.add_argument(
        "--synthetic-demo",
        action="store_true",
        help="Skip Binance; write deterministic 5m bars for offline bridge + A/B tests",
    )
    p.add_argument(
        "--synthetic-bars",
        type=int,
        default=52000,
        help="With --synthetic-demo, number of 5m bars (~52000 ≈ 18 months)",
    )
    p.add_argument("--synthetic-seed", type=int, default=1729, help="RNG seed for --synthetic-demo")
    args = p.parse_args()

    if args.synthetic_demo:
        summary = seed_synthetic_bars(
            db_path=args.db,
            canonical_symbol=args.canonical_symbol,
            tick_symbol=args.binance_symbol.upper(),
            bar_count=max(5000, args.synthetic_bars),
            seed=args.synthetic_seed,
        )
    else:
        summary = run_backfill(
            db_path=args.db,
            binance_symbol=args.binance_symbol.upper(),
            canonical_symbol=args.canonical_symbol,
            months=args.months,
            sleep_s=args.sleep,
            insecure_ssl=args.insecure_ssl,
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
