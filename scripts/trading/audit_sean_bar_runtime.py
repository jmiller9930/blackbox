#!/usr/bin/env python3
"""
Compare one Sean-reported 5m candle vs SQLite tape using the same rollup rules as the codebase.

Writes NDJSON debug lines to .cursor/debug-264225.log (session 264225).

Usage (from repo root):
  PYTHONPATH=scripts/runtime python3 scripts/trading/audit_sean_bar_runtime.py

Optional:
  BLACKBOX_MARKET_DATA_PATH=/path/to/market_data.db
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts" / "runtime"))

from _paths import default_market_data_path  # noqa: E402
from market_data.canonical_time import parse_iso_zulu_to_utc  # noqa: E402
from market_data.store import bar_membership_mode, ticks_in_bucket_5m  # noqa: E402
from market_data.canonical_bar import build_canonical_bar_from_ticks  # noqa: E402
from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP  # noqa: E402
from market_data.store import connect_market_db, ensure_market_schema  # noqa: E402
from _paths import repo_root  # noqa: E402

# region agent log
_DEBUG_LOG = _ROOT / ".cursor" / "debug-264225.log"
_SESSION = "264225"


def _agent_log(*, hypothesis_id: str, message: str, data: dict) -> None:
    payload = {
        "sessionId": _SESSION,
        "hypothesisId": hypothesis_id,
        "location": "audit_sean_bar_runtime.py",
        "message": message,
        "data": data,
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")


# endregion

# Sean external reference (2026-04-06 18:30 UTC bar)
SEAN_CANDLE_OPEN = "2026-04-06T18:30:00.000Z"
SEAN_O = 82.08428544
SEAN_H = 82.17884358
SEAN_L = 81.97395669
SEAN_C = 82.11571928
SEAN_V = 590


def main() -> int:
    db_path = default_market_data_path()
    sym = (os.environ.get("MARKET_TICK_SYMBOL") or "SOL-USD").strip() or "SOL-USD"

    # region agent log
    _agent_log(
        hypothesis_id="H0",
        message="audit_start",
        data={
            "db_path": str(db_path),
            "db_exists": db_path.is_file(),
            "MARKET_BAR_MEMBERSHIP": bar_membership_mode(),
            "PYTH_SSE_TICK_POLICY": (os.environ.get("PYTH_SSE_TICK_POLICY") or ""),
            "symbol": sym,
            "sean": {
                "candle_open": SEAN_CANDLE_OPEN,
                "O": SEAN_O,
                "H": SEAN_H,
                "L": SEAN_L,
                "C": SEAN_C,
                "V": SEAN_V,
            },
        },
    )
    # endregion

    if not db_path.is_file():
        # region agent log
        _agent_log(
            hypothesis_id="H1",
            message="missing_db",
            data={"db_path": str(db_path)},
        )
        # endregion
        print(f"No database at {db_path}", file=sys.stderr)
        return 2

    conn = connect_market_db(db_path)
    ensure_market_schema(conn, repo_root())
    open_utc = parse_iso_zulu_to_utc(SEAN_CANDLE_OPEN.replace(".000Z", "Z"))
    ticks = ticks_in_bucket_5m(conn, sym, open_utc)
    conn.close()

    # region agent log
    _agent_log(
        hypothesis_id="H1",
        message="tick_count_vs_sean",
        data={
            "our_tick_count": len(ticks),
            "sean_V": SEAN_V,
            "delta_V": len(ticks) - SEAN_V,
        },
    )
    # endregion

    bar = build_canonical_bar_from_ticks(
        ticks=ticks,
        tick_symbol=sym,
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=open_utc,
    )

    if bar is None:
        # region agent log
        _agent_log(
            hypothesis_id="H2",
            message="no_bar_from_ticks",
            data={"tick_count": len(ticks)},
        )
        # endregion
        print("No bar (no valid primary_price ticks in window).")
        return 1

    # region agent log
    _agent_log(
        hypothesis_id="H3",
        message="ohlc_compare",
        data={
            "our_O": bar.open,
            "our_H": bar.high,
            "our_L": bar.low,
            "our_C": bar.close,
            "our_V": bar.tick_count,
            "diff_O": bar.open - SEAN_O if bar.open is not None else None,
            "diff_H": bar.high - SEAN_H if bar.high is not None else None,
            "diff_L": bar.low - SEAN_L if bar.low is not None else None,
            "diff_C": bar.close - SEAN_C if bar.close is not None else None,
            "diff_V": bar.tick_count - SEAN_V,
        },
    )
    # endregion

    print(
        json.dumps(
            {
                "candle_open": SEAN_CANDLE_OPEN,
                "membership": bar_membership_mode(),
                "our_ticks": len(ticks),
                "our_ohlcv": {
                    "O": bar.open,
                    "H": bar.high,
                    "L": bar.low,
                    "C": bar.close,
                    "V": bar.tick_count,
                },
                "sean_ohlcv": {"O": SEAN_O, "H": SEAN_H, "L": SEAN_L, "C": SEAN_C, "V": SEAN_V},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
