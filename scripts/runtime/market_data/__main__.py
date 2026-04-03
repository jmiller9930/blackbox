"""python -m market_data — one-shot recorder (from scripts/runtime on PYTHONPATH)."""
from __future__ import annotations

import argparse
import json
import sys

from market_data.recorder import record_market_snapshot


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 5.1 — Pyth + Coinbase + optional Jupiter. With Jupiter, Jupiter is the gate anchor (king)."
    )
    p.add_argument("--symbol", default="SOL-USD", help="Logical symbol (default SOL-USD)")
    p.add_argument("--coinbase-product", default="SOL-USD", help="Coinbase product id")
    p.add_argument("--max-age-sec", type=float, default=120.0)
    p.add_argument(
        "--max-rel-diff",
        type=float,
        default=0.005,
        help="Max rel diff Pyth vs Coinbase when Jupiter is skipped/unavailable (fallback mode)",
    )
    p.add_argument(
        "--no-jupiter",
        action="store_true",
        help="Skip Jupiter quote (fallback: Pyth vs Coinbase only; same as MARKET_DATA_SKIP_JUPITER=1)",
    )
    p.add_argument(
        "--king-pyth-max-rel-diff",
        type=float,
        default=0.007,
        help="Jupiter king mode: max rel diff Pyth vs Jupiter (default 0.007)",
    )
    p.add_argument(
        "--king-coinbase-max-rel-diff",
        type=float,
        default=0.025,
        help="Jupiter king mode: max rel diff Coinbase vs Jupiter — wider support band (default 0.025)",
    )
    args = p.parse_args(argv)
    # Let recorder honor MARKET_DATA_SKIP_JUPITER unless CLI forces (--no-jupiter | default fetch).
    include_jupiter: bool | None
    if args.no_jupiter:
        include_jupiter = False
    else:
        include_jupiter = None  # recorder resolves env + default True when unset

    out = record_market_snapshot(
        symbol=args.symbol,
        coinbase_product=args.coinbase_product,
        max_age_sec=args.max_age_sec,
        max_rel_diff=args.max_rel_diff,
        include_jupiter=include_jupiter,
        king_pyth_max_rel_diff=args.king_pyth_max_rel_diff,
        king_coinbase_max_rel_diff=args.king_coinbase_max_rel_diff,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("gate", {}).get("state") != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
