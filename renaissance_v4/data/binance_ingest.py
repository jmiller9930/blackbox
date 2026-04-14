"""
binance_ingest.py

Purpose:
Download historical Binance 5-minute klines and store them in SQLite.

Usage:
Run directly to backfill approximately two years of SOLUSDT 5m data.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

from renaissance_v4.utils.db import get_connection

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
SYMBOL = "SOLUSDT"
INTERVAL = "5m"
LIMIT = 1000
FIVE_MINUTES_MS = 5 * 60 * 1000


def fetch_klines(symbol: str, interval: str, start_time_ms: int, end_time_ms: int) -> list[list]:
    """
    Fetch one batch of klines from Binance.
    Prints the request URL and response size for debugging.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": LIMIT,
    }
    url = f"{BINANCE_KLINES_URL}?{urlencode(params)}"
    print(f"[ingest] Requesting: {url}")

    with urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    print(f"[ingest] Received {len(payload)} bars")
    return payload


def insert_klines(connection: sqlite3.Connection, symbol: str, klines: list[list]) -> None:
    """
    Insert bars into SQLite using INSERT OR IGNORE so reruns stay safe.
    """
    print(f"[ingest] Inserting {len(klines)} rows into market_bars_5m")
    connection.executemany(
        """
        INSERT OR IGNORE INTO market_bars_5m (
            symbol, open_time, open, high, low, close, volume, close_time,
            quote_volume, trade_count, taker_base_volume, taker_quote_volume
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                symbol,
                row[0],
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
                row[6],
                float(row[7]),
                int(row[8]),
                float(row[9]),
                float(row[10]),
            )
            for row in klines
        ],
    )
    connection.commit()
    print("[ingest] Commit complete")


def main() -> None:
    """
    Backfill approximately two years of 5-minute SOLUSDT bars from Binance.
    This routine advances forward in time one batch at a time and prints progress.
    """
    connection = get_connection()

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=730)
    cursor_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    print(f"[ingest] Starting ingest for {SYMBOL}")
    print(f"[ingest] From: {start.isoformat()}")
    print(f"[ingest] To:   {now.isoformat()}")

    while cursor_ms < end_ms:
        batch = fetch_klines(SYMBOL, INTERVAL, cursor_ms, end_ms)

        if not batch:
            print("[ingest] No more bars returned; stopping")
            break

        insert_klines(connection, SYMBOL, batch)

        last_open_time = int(batch[-1][0])
        next_cursor_ms = last_open_time + FIVE_MINUTES_MS

        if next_cursor_ms <= cursor_ms:
            raise RuntimeError("[ingest] Cursor failed to advance; aborting")

        cursor_ms = next_cursor_ms
        print(f"[ingest] Advanced cursor to: {cursor_ms}")
        time.sleep(0.25)

    print("[ingest] Historical ingest completed successfully")


if __name__ == "__main__":
    main()
