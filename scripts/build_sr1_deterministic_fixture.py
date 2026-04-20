#!/usr/bin/env python3
"""
Build the **fixed** SQLite used for SR-1 (E2E v2.1): same bytes every run.

* Path: ``runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3``
* Symbol: **SOLUSDT** (must match manifests)
* Bars: **8000** × 5m, deterministic monotonic uptrend + controlled noise (produces ``trend_up`` + trades when paired with ``sr1_deterministic_trade_proof_v1.json``).

Run from repo root::

  python3 scripts/build_sr1_deterministic_fixture.py

Exit 0 after write.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


SYMBOL = "SOLUSDT"
BAR_MS = 5 * 60 * 1000
BASE_MS = 1_700_000_000_000
NUM_BARS = 8000


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_fixture_db(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    conn = sqlite3.connect(str(target))
    conn.execute(
        """CREATE TABLE market_bars_5m (
        symbol TEXT, open_time INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL,
        close_time INTEGER, quote_volume REAL, trade_count INTEGER, taker_base_volume REAL, taker_quote_volume REAL
    )"""
    )
    price = 100.0
    for i in range(NUM_BARS):
        t = BASE_MS + i * BAR_MS
        pct = (i + 1) / float(NUM_BARS)
        c_base = 100.0 + 600.0 * (pct**1.2)
        o = price
        noise = 3.0 * (1 if i % 5 != 0 else -2.0)
        c = max(o + 0.01, c_base + noise * 0.01)
        h = max(o, c) + abs(noise)
        l = min(o, c) - abs(noise)
        vol = 10000.0
        conn.execute(
            """INSERT INTO market_bars_5m (
            symbol, open_time, open, high, low, close, volume, close_time, quote_volume, trade_count,
            taker_base_volume, taker_quote_volume) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (SYMBOL, t, o, h, l, c, vol, t + BAR_MS - 1, 0.0, 0, 0.0, 0.0),
        )
        price = c
    conn.commit()
    conn.close()


def main() -> int:
    root = _repo_root()
    target = root / "runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3"
    build_fixture_db(target)
    print(f"[build_sr1_deterministic_fixture] wrote {target} ({NUM_BARS} bars, {SYMBOL})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
