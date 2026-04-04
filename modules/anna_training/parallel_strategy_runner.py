"""Parallel Anna paper strategies per market_event_id — no gating; ledger writes."""

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


def _parallel_strategy_ids() -> list[str]:
    raw = (os.environ.get("ANNA_PARALLEL_STRATEGY_IDS") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    from modules.anna_training.strategy_catalog import load_strategy_catalog

    out: list[str] = []
    for row in load_strategy_catalog():
        sid = str(row.get("id") or "").strip()
        if not sid or sid == "manual_operator_v1":
            continue
        out.append(sid)
    return out if out else ["jupiter_supertrend_ema_rsi_atr_v1"]


def _stub_pnl_for_strategy(strategy_id: str, market_event_id: str) -> tuple[str, float]:
    """Deterministic won/lost/breakeven + pnl for parallel paper harness (not venue truth)."""
    h = hashlib.sha256(f"{strategy_id}|{market_event_id}".encode()).hexdigest()
    v = int(h[:8], 16)
    bucket = v % 100
    if bucket < 40:
        return "lost", -round((v % 200) / 100.0 + 0.01, 2)
    if bucket < 65:
        return "breakeven", round(((v % 21) - 10) / 100.0, 2)
    return "won", round((v % 500) / 100.0 + 0.01, 2)


def run_parallel_anna_strategies_tick() -> dict[str, Any]:
    """
    For each configured Anna strategy, append one **paper** execution row for the **latest**
    ``market_event_id`` (from ``market_bars_5m``). Independent of Jack / single harness.

    Env:
      ANNA_PARALLEL_STRATEGY_RUNNER — default **on**; set ``0`` to disable.
      ANNA_PARALLEL_STRATEGY_IDS — optional comma list; else catalog-derived (excludes manual-only).
    """
    if not _env_bool("ANNA_PARALLEL_STRATEGY_RUNNER", True):
        return {"enabled": False, "reason": "ANNA_PARALLEL_STRATEGY_RUNNER off"}

    _ensure_runtime_path()
    from market_data.bar_lookup import fetch_latest_bar_row, fetch_latest_market_event_id

    from modules.anna_training.execution_ledger import (
        RESERVED_STRATEGY_BASELINE,
        append_execution_trade,
        connect_ledger,
        ensure_execution_ledger_schema,
        sync_strategy_registry_from_catalog,
    )

    mid = fetch_latest_market_event_id()
    if not mid:
        return {"ok": False, "reason": "no_market_event_id", "trades_written": 0}

    bar = fetch_latest_bar_row() or {}
    close_px = bar.get("close")
    o_px = bar.get("open")
    hi = bar.get("high")
    lo = bar.get("low")
    ctx = {
        "bar": {
            "open": o_px,
            "high": hi,
            "low": lo,
            "close": close_px,
            "market_event_id": mid,
        },
        "runner": "parallel_strategy_runner_v1",
    }

    strategies = _parallel_strategy_ids()
    written: list[str] = []

    conn = connect_ledger()
    try:
        ensure_execution_ledger_schema(conn)
        sync_strategy_registry_from_catalog(conn)
    finally:
        conn.close()

    for sid in strategies:
        if sid == RESERVED_STRATEGY_BASELINE:
            continue
        result, pnl = _stub_pnl_for_strategy(sid, mid)
        tid = _trade_id_for(sid, mid)
        try:
            append_execution_trade(
                trade_id=tid,
                strategy_id=sid,
                lane="anna",
                mode="paper",
                market_event_id=mid,
                symbol="SOL-PERP",
                timeframe="5m",
                side="long",
                entry_time=bar.get("candle_open_utc"),
                entry_price=float(close_px) if close_px is not None else None,
                size=1.0,
                exit_time=bar.get("candle_close_utc"),
                exit_price=float(close_px) if close_px is not None else None,
                exit_reason="CLOSE",
                pnl_usd=float(pnl),
                context_snapshot={"stub": True, "result": result, **ctx},
                notes=f"parallel_stub result={result}",
            )
            written.append(tid)
        except sqlite3.IntegrityError:
            # Idempotent re-run for same strategy+market_event_id (fixed trade_id).
            pass

    return {
        "ok": True,
        "market_event_id": mid,
        "strategies": strategies,
        "trades_written": len(written),
        "trade_ids": written,
    }


def _trade_id_for(strategy_id: str, market_event_id: str) -> str:
    h = hashlib.sha256(f"{strategy_id}|{market_event_id}|parallel_v1".encode()).hexdigest()[:24]
    return f"pt_{h}"
