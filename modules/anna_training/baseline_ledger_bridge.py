"""Baseline → execution_ledger: **Jupiter_2 Sean policy** (signal-gated) or legacy mechanical row.

Default **signal mode** env value is still ``sean_jupiter_v1`` (historic name; do not read as “old Jupiter policy”).
The evaluator is **only** ``modules/anna_training/jupiter_2_sean_policy.evaluate_jupiter_2_sean`` via
``sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v1`` (adapter over Jupiter_2).

**Execution trades:** still **at most one** baseline ``execution_trades`` row per ``market_event_id`` when the policy fires.

**Policy evaluations:** every evaluated tick writes/upserts ``policy_evaluations`` (including ``trade=false``),
for backtest joins to ``market_bars_5m``. Disable with ``BASELINE_POLICY_EVALUATION_LOG=0``.

Legacy: ``BASELINE_LEDGER_SIGNAL_MODE=legacy_mechanical_long`` — old open→close long every bar (lab only).
"""

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


def _policy_evaluation_log_enabled() -> bool:
    return _env_bool("BASELINE_POLICY_EVALUATION_LOG", True)


def _legacy_mechanical_allowed() -> bool:
    """Lab-only OHLC-long-every-bar path. Off by default (integrity: Sean policy is authoritative)."""
    return _env_bool("BASELINE_LEGACY_MECHANICAL_ALLOWED", False)


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


def _signal_mode() -> str:
    raw = (os.environ.get("BASELINE_LEDGER_SIGNAL_MODE") or "sean_jupiter_v1").strip().lower()
    if raw in ("legacy", "legacy_mechanical", "legacy_mechanical_long", "mechanical"):
        return "legacy_mechanical_long"
    return "sean_jupiter_v1"


def run_baseline_ledger_bridge_tick(
    *,
    market_data_db_path: Path | None = None,
    execution_ledger_db_path: Path | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """
    Append **at most one** baseline row per ``market_event_id`` when Sean Jupiter signal (or legacy) fires.

    Env:
      BASELINE_LEDGER_BRIDGE — default **on**; ``0`` disables all baseline writes.
      BASELINE_LEDGER_SIGNAL_MODE — ``sean_jupiter_v1`` (default) | ``legacy_mechanical_long``.
      BASELINE_LEGACY_MECHANICAL_ALLOWED — default **off**; ``1`` required for ``legacy_mechanical_long`` (lab only).
      BASELINE_LEDGER_MODE — ``paper`` (default) or ``live``.
      BASELINE_POLICY_EVALUATION_LOG — default **on**; ``0`` skips ``policy_evaluations`` upserts only.
    """
    if not _env_bool("BASELINE_LEDGER_BRIDGE", True):
        return {"enabled": False, "reason": "BASELINE_LEDGER_BRIDGE off"}

    _ensure_runtime_path()
    from market_data.bar_lookup import fetch_latest_bar_row, fetch_recent_bars_asc

    m = (mode or os.environ.get("BASELINE_LEDGER_MODE") or "paper").strip().lower()
    if m not in ("live", "paper"):
        m = "paper"

    sm = _signal_mode()
    if sm == "legacy_mechanical_long" and not _legacy_mechanical_allowed():
        return {
            "ok": False,
            "reason": "legacy_mechanical_long_disabled",
            "detail": "Mechanical OHLC baseline is quarantined. Set BASELINE_LEGACY_MECHANICAL_ALLOWED=1 for lab-only use.",
            "signal_mode": sm,
        }

    bar = fetch_latest_bar_row(db_path=market_data_db_path)
    if not bar:
        return {"ok": False, "reason": "no_canonical_bar"}

    mid = verify_market_event_id_matches_canonical_bar(bar)
    o = bar.get("open")
    c = bar.get("close")
    if o is None or c is None:
        return {"ok": False, "reason": "bar_missing_ohlc", "market_event_id": mid}
    if sm == "legacy_mechanical_long":
        return _run_legacy_mechanical_long(
            bar=bar,
            mid=mid,
            mode=m,
            execution_ledger_db_path=execution_ledger_db_path,
        )

    bars_asc = fetch_recent_bars_asc(limit=280, db_path=market_data_db_path)
    if not bars_asc or str(bars_asc[-1].get("market_event_id") or "") != mid:
        return {"ok": False, "reason": "bar_history_mismatch", "market_event_id": mid}

    from modules.anna_training.sean_jupiter_baseline_signal import evaluate_sean_jupiter_baseline_v1

    sig = evaluate_sean_jupiter_baseline_v1(bars_asc=bars_asc)
    if _policy_evaluation_log_enabled():
        from modules.anna_training.execution_ledger import upsert_policy_evaluation

        feat = dict(sig.features) if sig.features else {}
        try:
            upsert_policy_evaluation(
                market_event_id=mid,
                signal_mode=sm,
                tick_mode=m,
                trade=bool(sig.trade),
                reason_code=str(sig.reason_code or ""),
                features=feat,
                side=str(sig.side) if sig.trade else "flat",
                pnl_usd=(float(sig.pnl_usd) if sig.pnl_usd is not None else 0.0) if sig.trade else None,
                db_path=execution_ledger_db_path,
            )
        except sqlite3.OperationalError:
            # Readonly/locked ledger: still return policy outcome (do not abort tick).
            pass
    if not sig.trade:
        return {
            "ok": True,
            "no_trade": True,
            "market_event_id": mid,
            "reason_code": sig.reason_code,
            "features": sig.features,
            "signal_mode": sm,
        }

    size = 1.0
    tid = _baseline_trade_id(mid, m)
    pnl = float(sig.pnl_usd) if sig.pnl_usd is not None else 0.0

    from .decision_trace import persist_baseline_trade_with_trace
    from modules.anna_training.jupiter_2_sean_policy import (
        CATALOG_ID as baseline_catalog_id,
        POLICY_ENGINE_ID,
    )

    catalog_id = baseline_catalog_id
    ctx = {
        "source": "baseline_ledger_bridge_sean_jupiter_v1",
        "policy_engine": POLICY_ENGINE_ID,
        "trade_policy": "jupiter_perps",
        "catalog_strategy_id": catalog_id,
        "signal_mode": sm,
        "reason_code": sig.reason_code,
        "features": sig.features,
        "side": sig.side,
    }
    notes = (
        f"baseline — Jupiter_2 Sean policy ({catalog_id}) signal; "
        f"{sig.reason_code} side={sig.side}"
    )

    try:
        out = persist_baseline_trade_with_trace(
            market_event_id=mid,
            bar=bar,
            mode=m,
            trade_id=tid,
            pnl_usd=pnl,
            context_snapshot=ctx,
            notes=notes,
            db_path=execution_ledger_db_path,
            side=sig.side,
            economic_basis="jupiter_2_sean_entry_open_to_close",
            signal_snapshot=dict(sig.features),
        )
    except sqlite3.IntegrityError:
        return {
            "ok": True,
            "idempotent_skip": True,
            "market_event_id": mid,
            "trade_id": tid,
        }

    row = out.get("execution_trade")
    trace_meta = {k: v for k, v in out.items() if k != "execution_trade"}

    return {
        "ok": True,
        "market_event_id": mid,
        "trade_id": tid,
        "mode": m,
        "execution_trade": row,
        "decision_trace": trace_meta,
        "signal_mode": sm,
        "side": sig.side,
    }


def _run_legacy_mechanical_long(
    *,
    bar: dict[str, Any],
    mid: str,
    mode: str,
    execution_ledger_db_path: Path | None,
) -> dict[str, Any]:
    from .decision_trace import persist_baseline_trade_with_trace
    from .execution_ledger import compute_pnl_usd, upsert_policy_evaluation

    o = bar.get("open")
    c = bar.get("close")
    size = 1.0
    tid = _baseline_trade_id(mid, mode)
    pnl = compute_pnl_usd(entry_price=float(o), exit_price=float(c), size=size, side="long")

    tm = mode if mode in ("live", "paper") else "paper"
    if _policy_evaluation_log_enabled():
        try:
            upsert_policy_evaluation(
                market_event_id=mid,
                signal_mode="legacy_mechanical_long",
                tick_mode=tm,
                trade=True,
                reason_code="legacy_mechanical_long",
                features={
                    "source": "baseline_ledger_bridge_v1",
                    "economic_basis": "canonical_bar_open_to_close_long_1unit",
                    "price_source": bar.get("price_source"),
                    "tick_count": bar.get("tick_count"),
                },
                side="long",
                pnl_usd=pnl,
                db_path=execution_ledger_db_path,
            )
        except sqlite3.OperationalError:
            pass

    try:
        out = persist_baseline_trade_with_trace(
            market_event_id=mid,
            bar=bar,
            mode=mode,
            trade_id=tid,
            pnl_usd=pnl,
            context_snapshot={
                "source": "baseline_ledger_bridge_v1",
                "price_source": bar.get("price_source"),
                "tick_count": bar.get("tick_count"),
                "economic_basis": "canonical_bar_open_to_close_long_1unit",
            },
            notes="legacy mechanical baseline — OHLC long 1 unit (not Sean signal)",
            db_path=execution_ledger_db_path,
            side="long",
            economic_basis="canonical_bar_open_to_close_long_1unit",
            signal_snapshot=None,
        )
    except sqlite3.IntegrityError:
        return {
            "ok": True,
            "idempotent_skip": True,
            "market_event_id": mid,
            "trade_id": tid,
        }

    row = out.get("execution_trade")
    trace_meta = {k: v for k, v in out.items() if k != "execution_trade"}

    return {
        "ok": True,
        "market_event_id": mid,
        "trade_id": tid,
        "mode": mode,
        "execution_trade": row,
        "decision_trace": trace_meta,
        "signal_mode": "legacy_mechanical_long",
    }
