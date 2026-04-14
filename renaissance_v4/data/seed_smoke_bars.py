"""
seed_smoke_bars.py

Purpose:
Insert ≥ MIN_ROWS_REQUIRED synthetic SOLUSDT 5m bars for smoke tests (determinism, CI).

Usage:
  PYTHONPATH=. python3 -m renaissance_v4.data.seed_smoke_bars

Not for research — only deterministic pipeline proof.

Version:
v1.0

Change History:
- v1.0 Baseline v1 acceptance (architect determinism check).
"""

from __future__ import annotations

import sqlite3

from renaissance_v4.utils.db import DB_PATH, get_connection

SYMBOL = "SOLUSDT"
BAR_MS = 5 * 60 * 1000
NUM_BARS = 60
BASE_MS = 1_700_000_000_000


def main() -> None:
    connection = get_connection()
    rows: list[tuple] = []
    price = 100.0
    t = BASE_MS
    for _i in range(NUM_BARS):
        o = price
        c = price + 0.01
        h = max(o, c) + 0.02
        l = min(o, c) - 0.02
        vol = 1000.0
        rows.append(
            (
                SYMBOL,
                t,
                o,
                h,
                l,
                c,
                vol,
                t + BAR_MS - 1,
                0.0,
                0,
                0.0,
                0.0,
            )
        )
        price = c
        t += BAR_MS

    connection.executemany(
        """
        INSERT OR REPLACE INTO market_bars_5m (
            symbol, open_time, open, high, low, close, volume, close_time,
            quote_volume, trade_count, taker_base_volume, taker_quote_volume
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    connection.commit()
    n = connection.execute("SELECT COUNT(*) FROM market_bars_5m WHERE symbol = ?", (SYMBOL,)).fetchone()[0]
    print(f"[seed_smoke_bars] Wrote {NUM_BARS} bars; table count for {SYMBOL} = {n}")
    print(f"[seed_smoke_bars] Database: {DB_PATH.resolve()}")


if __name__ == "__main__":
    main()
