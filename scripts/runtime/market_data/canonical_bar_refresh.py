"""
Recompute and persist the last closed 5m bar from ticks (call after each tick ingest).

After a successful ``market_bars_5m`` upsert, optionally runs
:func:`modules.anna_training.baseline_ledger_bridge.run_baseline_ledger_bridge_tick` so
``policy_evaluations`` / baseline ``execution_trades`` stay aligned with ingest (not only the
Karpathy loop). Controlled by ``BASELINE_LEDGER_AFTER_CANONICAL_BAR`` (default on). Tests should set
``BASELINE_LEDGER_AFTER_CANONICAL_BAR=0`` when using isolated temp DBs without a matching ledger path.

Tick selection for the bucket follows ``MARKET_BAR_MEMBERSHIP`` (see
:func:`market_data.store.bar_membership_mode`): default **oracle publish time**
(Sean-aligned Hermes clock on ``pyth_hermes_sse`` rows).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from market_data.canonical_bar import build_canonical_bar_from_ticks
from market_data.canonical_instrument import TIMEFRAME_5M, canonical_symbol_for_tick_symbol
from market_data.canonical_time import format_candle_open_iso_z, last_closed_candle_open_utc
from market_data.store import ticks_in_bucket_5m, upsert_market_bar_5m

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _sqlite_main_database_path(conn: Any) -> Path | None:
    """Resolve the on-disk path of the main SQLite database (for passing to the baseline bridge)."""
    try:
        for row in conn.execute("PRAGMA database_list"):
            if len(row) >= 3 and row[1] == "main" and row[2]:
                return Path(str(row[2]))
    except Exception:
        return None
    return None


def _baseline_ledger_bridge_after_bar_refresh(conn: Any) -> dict[str, Any] | None:
    """
    Run baseline policy → ledger for the latest bar after ingest committed the canonical 5m row.

    Skips when ``BASELINE_LEDGER_AFTER_CANONICAL_BAR`` is off or the market DB path cannot be resolved.
    """
    raw = (os.environ.get("BASELINE_LEDGER_AFTER_CANONICAL_BAR") or "1").strip().lower()
    if raw in ("0", "false", "no", "off", ""):
        return None
    mp = _sqlite_main_database_path(conn)
    if mp is None or not mp.is_file():
        return {"skipped": True, "reason": "market_db_path_unresolved"}

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    from modules.anna_training.baseline_ledger_bridge import run_baseline_ledger_bridge_tick

    try:
        return run_baseline_ledger_bridge_tick(market_data_db_path=mp)
    except Exception as exc:  # noqa: BLE001 — surface any unexpected failure in status dict
        return {"ok": False, "reason": "baseline_ledger_bridge_exception", "error": repr(exc)}


def refresh_last_closed_bar_from_ticks(conn: Any, tick_symbol: str) -> dict[str, Any]:
    """
    Aggregate ticks for the **last closed** 5m bucket and upsert ``market_bars_5m``.

    Returns a small status dict for logging / tests.
    """
    canonical = canonical_symbol_for_tick_symbol(tick_symbol)
    last_open = last_closed_candle_open_utc()
    ticks = ticks_in_bucket_5m(conn, tick_symbol, last_open)
    bar = build_canonical_bar_from_ticks(
        ticks=ticks,
        tick_symbol=tick_symbol,
        canonical_symbol=canonical,
        candle_open_utc=last_open,
        timeframe=TIMEFRAME_5M,
    )
    if bar is None:
        return {
            "ok": False,
            "reason": "no_ticks_in_closed_bucket",
            "tick_symbol": tick_symbol,
            "canonical_symbol": canonical,
            "candle_open_utc": format_candle_open_iso_z(last_open),
            "tick_count": len(ticks),
        }
    upsert_market_bar_5m(conn, bar)
    out: dict[str, Any] = {
        "ok": True,
        "market_event_id": bar.market_event_id,
        "canonical_symbol": canonical,
        "candle_open_utc": format_candle_open_iso_z(last_open),
        "tick_count": bar.tick_count,
    }
    bridge = _baseline_ledger_bridge_after_bar_refresh(conn)
    if bridge is not None:
        out["baseline_ledger_bridge"] = bridge
    return out
