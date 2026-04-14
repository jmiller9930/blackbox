#!/usr/bin/env python3
"""
Run :func:`market_data.binance_strategy_bars_sync.sync_binance_strategy_bars_into_db` on an interval.

Intended for Docker Compose or systemd on the lab host (Binance reachable). Without this loop,
``binance_strategy_bars_5m`` only advances when the sync script is run manually — **hard temporal failure**
for Jupiter_3.

Environment:
  BINANCE_STRATEGY_SYNC_INTERVAL_SEC — seconds between runs (default ``30``, clamped 15..600).
  BLACKBOX_MARKET_DATA_PATH — same as API / pyth-sse-ingest.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_REPO_RUNTIME = Path(__file__).resolve().parent
if str(_REPO_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_REPO_RUNTIME))


def _interval_sec() -> float:
    try:
        v = float((os.environ.get("BINANCE_STRATEGY_SYNC_INTERVAL_SEC") or "30").strip())
    except ValueError:
        v = 30.0
    return max(15.0, min(600.0, v))


def main() -> None:
    from _paths import default_market_data_path
    from market_data.binance_strategy_bars_sync import sync_binance_strategy_bars_into_db

    db = default_market_data_path()
    interval = _interval_sec()
    print(
        f"binance_strategy_bars_sync_loop: start db={db} interval_sec={interval}",
        flush=True,
    )
    while True:
        t0 = time.perf_counter()
        try:
            out = sync_binance_strategy_bars_into_db(db_path=db)
            print(f"binance_strategy_bars_sync_loop: {json.dumps(out)}", flush=True)
        except Exception as exc:  # noqa: BLE001 — keep loop alive
            print(f"binance_strategy_bars_sync_loop: error {exc!r}", file=sys.stderr, flush=True)
        elapsed = time.perf_counter() - t0
        sleep_for = max(0.0, interval - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
