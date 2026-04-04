"""Baseline → execution_ledger: same market_event_id as Anna (canonical bar row, single constructor)."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _runtime_scripts() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "runtime"


def _ensure_runtime_path() -> None:
    rt = _runtime_scripts()
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))


def verify_market_event_id_matches_canonical_bar(bar: dict[str, Any]) -> str:
    """
    Recompute ``market_event_id`` via :func:`make_market_event_id` from the bar's open time
    and assert it equals the stored ``market_event_id`` (no divergence from Anna path).
    """
    _ensure_runtime_path()
    from market_data.market_event_id import make_market_event_id
    from market_data.canonical_time import parse_iso_zulu_to_utc

    stored = str(bar.get("market_event_id") or "").strip()
    sym = str(bar.get("canonical_symbol") or "").strip()
    tf = str(bar.get("timeframe") or "").strip()
    op_s = str(bar.get("candle_open_utc") or "").strip()
    if not stored or not sym or not tf or not op_s:
        raise ValueError("bar_missing_identity_fields")
    op = parse_iso_zulu_to_utc(op_s)
    computed = make_market_event_id(canonical_symbol=sym, candle_open_utc=op, timeframe=tf)
    if computed != stored:
        raise ValueError(f"market_event_id_divergence stored={stored!r} recomputed={computed!r}")
    return stored


def _baseline_trade_id(market_event_id: str, mode: str) -> str:
    h = hashlib.sha256(f"baseline|{market_event_id}|{mode}|v1".encode()).hexdigest()[:24]
    return f"bl_{h}"


def run_baseline_ledger_bridge_tick(
    *,
    market_data_db_path: Path | None = None,
    execution_ledger_db_path: Path | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """
    Append one **baseline** row to ``execution_trades`` for the latest canonical 5m bar.

    Uses **only** ``market_event_id`` and OHLC from ``market_bars_5m`` (same source as Anna).
    Economic fields: long 1 unit notional, entry at bar **open**, exit at bar **close**,
    P&amp;L = (close - open) * size (index-style USD move on SOL-PERP).

    Env:
      BASELINE_LEDGER_BRIDGE — default **on**; ``0`` disables.
      BASELINE_LEDGER_MODE — ``paper`` (default) or ``live``.
    """
    if not _env_bool("BASELINE_LEDGER_BRIDGE", True):
        return {"enabled": False, "reason": "BASELINE_LEDGER_BRIDGE off"}

    _ensure_runtime_path()
    from market_data.bar_lookup import fetch_latest_bar_row

    m = (mode or os.environ.get("BASELINE_LEDGER_MODE") or "paper").strip().lower()
    if m not in ("live", "paper"):
        m = "paper"

    bar = fetch_latest_bar_row(db_path=market_data_db_path)
    if not bar:
        return {"ok": False, "reason": "no_canonical_bar"}

    mid = verify_market_event_id_matches_canonical_bar(bar)
    o = bar.get("open")
    c = bar.get("close")
    if o is None or c is None:
        return {"ok": False, "reason": "bar_missing_ohlc", "market_event_id": mid}

    size = 1.0
    tid = _baseline_trade_id(mid, m)

    from .execution_ledger import RESERVED_STRATEGY_BASELINE, append_execution_trade

    try:
        row = append_execution_trade(
            trade_id=tid,
            strategy_id=RESERVED_STRATEGY_BASELINE,
            lane="baseline",
            mode=m,
            market_event_id=mid,
            symbol=str(bar.get("canonical_symbol") or "SOL-PERP"),
            timeframe=str(bar.get("timeframe") or "5m"),
            side="long",
            entry_time=str(bar.get("candle_open_utc") or ""),
            entry_price=float(o),
            size=size,
            exit_time=str(bar.get("candle_close_utc") or ""),
            exit_price=float(c),
            exit_reason="CLOSE",
            context_snapshot={
                "source": "baseline_ledger_bridge_v1",
                "price_source": bar.get("price_source"),
                "tick_count": bar.get("tick_count"),
                "economic_basis": "canonical_bar_open_to_close_long_1unit",
            },
            notes="baseline bridge — OHLC from same market_bars_5m row as Anna market_event_id",
            db_path=execution_ledger_db_path,
        )
    except sqlite3.IntegrityError:
        return {
            "ok": True,
            "idempotent_skip": True,
            "market_event_id": mid,
            "trade_id": tid,
        }

    return {
        "ok": True,
        "market_event_id": mid,
        "trade_id": tid,
        "mode": m,
        "execution_trade": row,
    }
