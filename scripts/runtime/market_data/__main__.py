"""python -m market_data — one-shot recorder (from scripts/runtime on PYTHONPATH)."""
from __future__ import annotations

import argparse
import json
import sys

from market_data.recorder import record_market_snapshot


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 5.1 — record one Pyth+Coinbase snapshot to market_data.db")
    p.add_argument("--symbol", default="SOL-USD", help="Logical symbol (default SOL-USD)")
    p.add_argument("--coinbase-product", default="SOL-USD", help="Coinbase product id")
    p.add_argument("--max-age-sec", type=float, default=120.0)
    p.add_argument("--max-rel-diff", type=float, default=0.005)
    args = p.parse_args(argv)
    out = record_market_snapshot(
        symbol=args.symbol,
        coinbase_product=args.coinbase_product,
        max_age_sec=args.max_age_sec,
        max_rel_diff=args.max_rel_diff,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("gate", {}).get("state") != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
