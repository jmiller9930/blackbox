"""
Finite search-space and workload estimates for pattern-game / replay.

Operators often ask: how many combinations exist, and how long will parallel batches take?
This module uses **countable** inputs: catalog entries, SQLite bar count, and your batch size.

Notes:
- **Non-empty signal subsets** = 2^M - 1 where M is the number of catalog ``signals`` (unordered
  on/off membership). Not every subset may pass ``validate_manifest_against_catalog`` — this is an
  upper bound on *distinct signal sets*, not a guarantee every combo is valid.
- **One replay** walks the full loaded bar series once per scenario; work scales with
  ``scenario_count * bars`` (roughly), divided across workers for independent scenarios.
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from renaissance_v4.utils.db import DB_PATH

_CATALOG = Path(__file__).resolve().parents[1] / "registry" / "catalog_v1.json"


def _load_catalog() -> dict[str, Any]:
    raw = _CATALOG.read_text(encoding="utf-8")
    return json.loads(raw)


def count_market_bars() -> tuple[int | None, str | None]:
    """Return (row_count, error_message). None count if DB missing or query fails."""
    path = DB_PATH.resolve()
    if not path.is_file():
        return None, f"database not found at {path}"
    try:
        con = sqlite3.connect(str(path))
        try:
            cur = con.execute("SELECT COUNT(*) FROM market_bars_5m")
            row = cur.fetchone()
            n = int(row[0]) if row else 0
        finally:
            con.close()
        return n, None
    except sqlite3.Error as e:
        return None, str(e)


def build_search_space_estimate(
    *,
    batch_size: int | None = None,
    workers: int | None = None,
) -> dict[str, Any]:
    """
    JSON-serializable estimate for APIs and CLI.

    ``batch_size`` / ``workers`` are optional hints for parallel batch math (ceil(batch/workers)).
    """
    cat = _load_catalog()
    signals = cat.get("signals") or []
    fusion_engines = cat.get("fusion_engines") or []
    regimes = cat.get("regime_classifiers") or []
    risk_models = cat.get("risk_models") or []
    m = len(signals)
    non_empty_subsets = (2**m - 1) if m > 0 else 0

    bars, dberr = count_market_bars()

    w = max(1, int(workers or 1))
    bs = max(0, int(batch_size or 0))
    parallel_rounds: int | None = None
    if bs > 0:
        parallel_rounds = int(math.ceil(bs / w))

    return {
        "catalog_path": str(_CATALOG.resolve()),
        "catalog": {
            "signals_count": m,
            "fusion_engines_count": len(fusion_engines),
            "regime_classifiers_count": len(regimes),
            "risk_models_count": len(risk_models),
        },
        "combinatorics": {
            "non_empty_signal_subsets_upper_bound": non_empty_subsets,
            "explanation": (
                f"With {m} registered signals, there are 2^{m} subsets including the empty set; "
                f"non-empty subsets = 2^{m} - 1 = {non_empty_subsets}. "
                "Manifest validation may reject some subsets; order in JSON is fixed by your recipe."
            ),
        },
        "dataset": {
            "database_path": str(DB_PATH.resolve()),
            "market_bars_5m_count": bars,
            "error": dberr,
        },
        "workload_hints": {
            "batch_size_for_parallel_math": bs if bs > 0 else None,
            "workers_assumed": w if bs > 0 else None,
            "parallel_rounds_ceil_batch_over_workers": parallel_rounds,
            "explanation": (
                "Each scenario runs one full-history replay (bar walk). "
                "Independent scenarios divide across workers; rounds ≈ ceil(batch_size / workers)."
            ),
        },
        "bar_replay_units": (
            (bs * bars) if bars is not None and bs > 0 else None
        ),
        "bar_replay_units_note": (
            "scenario_count × bar_count is a coarse scalar for total bar steps if each replay "
            "uses the full table (same as replay_runner)."
        ),
    }


def main() -> None:
    import argparse
    import pprint

    ap = argparse.ArgumentParser(description="Print catalog + dataset search-space estimate (JSON).")
    ap.add_argument("--batch-size", type=int, default=None, help="Scenario count for parallel/bars hints")
    ap.add_argument("--workers", type=int, default=None, help="Workers for ceil(batch/workers)")
    args = ap.parse_args()
    pprint.pprint(build_search_space_estimate(batch_size=args.batch_size, workers=args.workers))


if __name__ == "__main__":
    main()
