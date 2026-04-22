#!/usr/bin/env python3
"""
Append SOLUSDT 5m bars with a strong uptrend so replay can leave volatility_compression
and close at least one trade (Student carousel proof).

Uses RENAISSANCE_V4_DB_PATH when set; otherwise default repo sqlite (typically gitignored).

Idempotent: skips rows that already exist (same symbol, open_time).
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Set before importing db if you rely on override — db module reads env at import
from renaissance_v4.utils import db as dbmod  # noqa: E402

N_NEW = 180
STEP_MS = 300_000  # 5m
SYMBOL = "SOLUSDT"


def main() -> None:
    p = dbmod.DB_PATH
    print(f"DB: {p}", flush=True)
    if not p.is_file():
        print("error: database file missing", file=sys.stderr)
        sys.exit(1)
    con = sqlite3.connect(p)
    cur = con.cursor()
    row = cur.execute(
        "select open_time, close from market_bars_5m where symbol=? order by open_time desc limit 1",
        (SYMBOL,),
    ).fetchone()
    if not row:
        print("error: no SOLUSDT bars", file=sys.stderr)
        sys.exit(1)
    last_t, last_c = int(row[0]), float(row[1])
    t0 = last_t + STEP_MS
    inserted = 0
    for i in range(N_NEW):
        ot = t0 + i * STEP_MS
        exists = cur.execute(
            "select 1 from market_bars_5m where symbol=? and open_time=? limit 1",
            (SYMBOL, ot),
        ).fetchone()
        if exists:
            continue
        base = last_c + (i + 1) * 0.35  # strong drift
        o = base - 0.02
        h = base + 0.25
        l = base - 0.08
        c = base + 0.18
        vol = 8000.0 + i * 10.0
        ct = ot + 299_000
        cur.execute(
            """
            insert into market_bars_5m
            (symbol, open_time, open, high, low, close, volume, close_time,
             quote_volume, trade_count, taker_base_volume, taker_quote_volume)
            values (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (SYMBOL, ot, o, h, l, c, vol, ct, None, None, None, None),
        )
        inserted += 1
    con.commit()
    n = cur.execute("select count(*) from market_bars_5m where symbol=?", (SYMBOL,)).fetchone()[0]
    con.close()
    print(f"Inserted {inserted} new bars; SOLUSDT total rows = {n}", flush=True)


if __name__ == "__main__":
    main()
