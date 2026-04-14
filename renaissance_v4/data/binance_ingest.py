"""
binance_ingest.py

Purpose:
Download historical Binance 5-minute klines and store them in SQLite.

Usage:
Run directly to backfill local historical market data for RenaissanceV4.

Version:
v1.0

Change History:
- v1.0 Initial implementation scaffold.
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


def fetch_klines(symbol: str, interval: str, start_time_ms: int, end_time_ms: int) -> list[list]:
    """
    Fetch a batch of klines from Binance and print request boundaries for debugging.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": LIMIT,
    }
    url = f"{BINANCE_KLINES_URL}?{urlencode(params)}"
    print(f"[ingest] Requesting klines: {url}")
    with urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    print(f"[ingest] Received {len(payload)} bars")
    return payload


def insert_klines(connection: sqlite3.Connection, symbol: str, klines: list[list]) -> None:
    """
    Insert kline rows into SQLite with INSERT OR IGNORE semantics.
    """
    print(f"[ingest] Inserting {len(klines)} bars into database")
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
    Backfill approximately two years of 5-minute SOLUSDT bars into SQLite.
    """
    connection = get_connection()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=730)
    cursor_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    print(f"[ingest] Starting backfill for {SYMBOL} from {start.isoformat()} to {now.isoformat()}")

    while cursor_ms < end_ms:
        batch = fetch_klines(SYMBOL, INTERVAL, cursor_ms, end_ms)
        if not batch:
            print("[ingest] No more data returned, stopping")
            break

        insert_klines(connection, SYMBOL, batch)

        last_open_time = int(batch[-1][0])
        next_cursor = last_open_time + (5 * 60 * 1000)
        if next_cursor <= cursor_ms:
            raise RuntimeError("[ingest] Cursor did not advance; aborting to avoid infinite loop")

        cursor_ms = next_cursor
        print(f"[ingest] Advanced cursor to: {cursor_ms}")
        time.sleep(0.25)

    print("[ingest] Historical backfill completed successfully")


if __name__ == "__main__":
    main()
