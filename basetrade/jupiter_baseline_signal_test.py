#!/usr/bin/env python3
"""
Jupiter trade policy — baseline signal test (parity harness).

Runs ``evaluate_sean_jupiter_baseline_v1`` against canonical ``market_bars_5m`` (same DB as production).
Optional: ``run_baseline_ledger_bridge_tick`` dry view (prints what the bridge would see).

Usage:

  ./basetrade/run_jupiter_baseline_test.sh
  ./basetrade/run_jupiter_baseline_test.sh --bridge-dry-run
  ./basetrade/run_jupiter_baseline_test.sh --json

Env:
  BLACKBOX_MARKET_DATA_PATH — default ``data/sqlite/market_data.db`` under repo root
  BLACKBOX_EXECUTION_LEDGER_PATH — only if ``--bridge-dry-run`` and you want ledger path echoed
  BASELINE_LEDGER_* — same as daemon (signal mode, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = _repo_root()
    rt = root / "scripts" / "runtime"
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    ap = argparse.ArgumentParser(description="Jupiter policy baseline signal test (lab / clawbot)")
    ap.add_argument(
        "--bridge-dry-run",
        action="store_true",
        help="Also call baseline_ledger_bridge_tick and print result (writes if BASELINE_LEDGER_BRIDGE=1).",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Single JSON object on stdout",
    )
    args = ap.parse_args()

    from market_data.bar_lookup import fetch_recent_bars_asc

    from modules.anna_training.sean_jupiter_baseline_signal import (
        MIN_BARS,
        evaluate_sean_jupiter_baseline_v1,
    )

    db_env = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or "").strip()
    db_path = Path(db_env).expanduser() if db_env else root / "data" / "sqlite" / "market_data.db"

    out: dict = {
        "market_db": str(db_path),
        "market_db_exists": db_path.is_file(),
        "min_bars_required": MIN_BARS,
    }

    if not db_path.is_file():
        out["error"] = "market_db_missing — ingest bars or set BLACKBOX_MARKET_DATA_PATH"
        print(json.dumps(out, indent=2))
        return 2

    bars = fetch_recent_bars_asc(limit=280, db_path=db_path)
    out["bars_fetched"] = len(bars)
    if len(bars) < MIN_BARS:
        out["error"] = f"need_at_least_{MIN_BARS}_bars"
        print(json.dumps(out, indent=2))
        return 3

    sig = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    out["signal"] = {
        "trade": sig.trade,
        "side": sig.side,
        "reason_code": sig.reason_code,
        "pnl_usd": sig.pnl_usd,
        "features": sig.features,
    }

    if args.bridge_dry_run:
        from modules.anna_training.baseline_ledger_bridge import run_baseline_ledger_bridge_tick

        bridge = run_baseline_ledger_bridge_tick(market_data_db_path=db_path)
        out["baseline_ledger_bridge_tick"] = bridge

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print("=== Jupiter policy baseline signal (parity harness) ===")
        print(f"market_db: {db_path}")
        print(f"bars_used: {len(bars)} (latest closed chain)")
        print(f"trade: {sig.trade}  side: {sig.side}  reason: {sig.reason_code}")
        if sig.pnl_usd is not None:
            print(f"pnl_usd (1 unit, open→close): {sig.pnl_usd}")
        print("features:")
        print(json.dumps(sig.features, indent=2))
        if args.bridge_dry_run:
            print("baseline_ledger_bridge_tick:")
            print(json.dumps(out.get("baseline_ledger_bridge_tick"), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
