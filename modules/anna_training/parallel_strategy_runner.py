"""Parallel Anna paper strategies per market_event_id — Sean Jupiter baseline signal (v2/v3 per operator slot)."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from modules.anna_training.sean_jupiter_baseline_signal import (
    evaluate_sean_jupiter_baseline_v1,
    evaluate_sean_jupiter_baseline_v3,
)
from modules.anna_training.store import load_state


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _parallel_strategy_mode() -> str:
    """
    ``paper`` — economic Anna lane rows (PnL in ledger; comparable vs baseline).
    ``paper_stub`` — legacy eval-only rows (**pnl_usd NULL**); breaks dashboard pairing.

    Default: **paper** (measurement instrument). Stub is allowed only when both:
    - ``ANNA_PARALLEL_STRATEGY_MODE`` is stub-like (``stub`` / ``paper_stub`` / ``eval``), and
    - ``ANNA_PARALLEL_STUB_LAB=1`` (explicit lab opt-in).

    This prevents a stray ``paper_stub`` host env from excluding every Anna cell (``missing_pnl``).
    """
    raw = (os.environ.get("ANNA_PARALLEL_STRATEGY_MODE") or "paper").strip().lower()
    if raw in ("paper", "economic", "economic_paper"):
        return "paper"
    if raw in ("stub", "paper_stub", "eval"):
        lab = (os.environ.get("ANNA_PARALLEL_STUB_LAB") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if lab:
            return "paper_stub"
        return "paper"
    return "paper"


def _runtime_scripts() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "runtime"


def _ensure_runtime_path() -> None:
    rt = _runtime_scripts()
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))


def _default_market_db_path() -> Path:
    env = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "sqlite" / "market_data.db"


def _migrate_anna_parallel_stub_rows_to_paper(
    conn: sqlite3.Connection,
    *,
    market_db_path: Path | None,
) -> dict[str, Any]:
    """
    One-time-per-row upgrade: legacy ``paper_stub`` parallel Anna rows stored ``pnl_usd`` NULL.
    Recompute economic long open→close PnL from ``market_bars_5m`` and set ``mode=paper``.
    """
    _ensure_runtime_path()
    from market_data.bar_lookup import fetch_bar_by_market_event_id

    from modules.anna_training.execution_ledger import compute_pnl_usd

    mpath = market_db_path or _default_market_db_path()
    if not mpath.is_file():
        return {"ok": False, "reason": "market_db_missing", "updated": 0}

    cur = conn.execute(
        """
        SELECT trade_id, market_event_id
        FROM execution_trades
        WHERE lane = 'anna' AND mode = 'paper_stub' AND pnl_usd IS NULL
          AND (notes IS NOT NULL AND notes NOT LIKE '%migrated_stub_to_paper%')
          AND (
            notes LIKE '%parallel_stub%' OR notes LIKE '%parallel_runner%'
          )
        """
    )
    rows = cur.fetchall()
    updated = 0
    for trade_id, mid in rows:
        tid = str(trade_id or "").strip()
        mid_s = str(mid or "").strip()
        if not tid or not mid_s:
            continue
        bar = fetch_bar_by_market_event_id(mid_s, db_path=mpath)
        if not bar:
            continue
        o = bar.get("open")
        c = bar.get("close")
        if o is None or c is None:
            continue
        try:
            ep = float(o)
            xp = float(c)
        except (TypeError, ValueError):
            continue
        pnl = compute_pnl_usd(entry_price=ep, exit_price=xp, size=1.0, side="long")
        cu = conn.execute(
            """
            UPDATE execution_trades
            SET mode = 'paper', pnl_usd = ?,
                notes = COALESCE(notes, '') || ' [migrated_stub_to_paper_v1]'
            WHERE trade_id = ? AND lane = 'anna' AND mode = 'paper_stub' AND pnl_usd IS NULL
            """,
            (pnl, tid),
        )
        if cu.rowcount and cu.rowcount > 0:
            updated += int(cu.rowcount)
    conn.commit()
    return {"ok": True, "updated": updated, "market_db_path": str(mpath)}


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
    return out if out else ["jupiter_2_sean_perps_v1"]


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


def run_parallel_anna_strategies_tick(
    *,
    market_data_db_path: Path | None = None,
    execution_ledger_db_path: Path | None = None,
) -> dict[str, Any]:
    """
    For **each** configured Anna strategy id, append **one** execution row for the **latest**
    ``market_event_id`` **only when** :func:`evaluate_sean_jupiter_baseline_v1` returns ``trade=True``
    (same Jupiter_2 policy as :func:`run_baseline_ledger_bridge_tick`; env ``BASELINE_LEDGER_SIGNAL_MODE`` default is still named ``sean_jupiter_v1`` for compatibility).
    **Multiple strategies** ⇒ multiple Anna rows on the **same** signal event (one per strategy id).

    Mode (``ANNA_PARALLEL_STRATEGY_MODE``, default ``paper``):
      - **paper** — economic Anna lane; ``pnl_usd`` from open→close in the **signal** direction (long or short), size 1.
      - **paper_stub** — legacy eval; no asserted PnL (synthetic classification in context only); still signal-gated.

    ``market_event_id`` is recomputed from the same canonical bar row via
    :func:`verify_market_event_id_matches_canonical_bar` (no divergence from the single constructor).

    Env:
      ANNA_PARALLEL_STRATEGY_RUNNER — default **on**; set ``0`` to disable.
      ANNA_PARALLEL_STRATEGY_IDS — optional comma list; else catalog-derived (excludes manual-only).
      ANNA_PARALLEL_STRATEGY_MODE — ``paper`` (default) or ``paper_stub``.
    """
    if not _env_bool("ANNA_PARALLEL_STRATEGY_RUNNER", True):
        return {"enabled": False, "reason": "ANNA_PARALLEL_STRATEGY_RUNNER off"}

    _ensure_runtime_path()
    from market_data.bar_lookup import (
        fetch_latest_bar_row,
        fetch_latest_bar_row_binance_strategy,
        fetch_latest_market_event_id,
        fetch_latest_market_event_id_binance_strategy,
        fetch_recent_bars_asc,
        fetch_recent_bars_asc_binance_strategy,
    )

    from modules.anna_training.baseline_ledger_bridge import verify_market_event_id_matches_canonical_bar
    from modules.anna_training.decision_trace import (
        persist_parallel_anna_paper_trade_with_trace,
        persist_parallel_anna_stub_trade_with_trace,
    )
    from modules.anna_training.execution_ledger import (
        BASELINE_POLICY_SLOT_JUP_V3,
        RESERVED_STRATEGY_BASELINE,
        connect_ledger,
        ensure_execution_ledger_schema,
        get_baseline_jupiter_policy_slot,
        signal_mode_for_baseline_policy_slot,
        sync_strategy_registry_from_catalog,
    )

    conn_slot = connect_ledger(execution_ledger_db_path)
    try:
        ensure_execution_ledger_schema(conn_slot)
        policy_slot_early = get_baseline_jupiter_policy_slot(conn_slot)
    finally:
        conn_slot.close()

    use_v3_early = policy_slot_early == BASELINE_POLICY_SLOT_JUP_V3
    if use_v3_early:
        mid = fetch_latest_market_event_id_binance_strategy(db_path=market_data_db_path)
        bar = fetch_latest_bar_row_binance_strategy(db_path=market_data_db_path) or {}
        bars_asc = fetch_recent_bars_asc_binance_strategy(db_path=market_data_db_path)
    else:
        mid = fetch_latest_market_event_id(db_path=market_data_db_path)
        bar = fetch_latest_bar_row(db_path=market_data_db_path) or {}
        bars_asc = fetch_recent_bars_asc(limit=280, db_path=market_data_db_path)

    if not mid:
        return {"ok": False, "reason": "no_market_event_id", "trades_written": 0}

    if not bar:
        return {
            "ok": False,
            "reason": "no_binance_strategy_bar" if use_v3_early else "no_canonical_bar",
            "trades_written": 0,
        }

    try:
        verified_mid = verify_market_event_id_matches_canonical_bar(bar)
    except ValueError as e:
        return {"ok": False, "reason": "market_event_id_divergence", "detail": str(e)}

    if verified_mid != mid:
        return {
            "ok": False,
            "reason": "mid_fetch_vs_bar_mismatch",
            "mid_fetch": mid,
            "mid_bar": verified_mid,
        }

    if not bars_asc or str(bars_asc[-1].get("market_event_id") or "") != mid:
        return {
            "ok": False,
            "reason": "bar_history_mismatch",
            "market_event_id": mid,
            "trades_written": 0,
        }

    close_px = bar.get("close")
    o_px = bar.get("open")
    hi = bar.get("high")
    lo = bar.get("low")
    base_ctx = {
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
    mode = _parallel_strategy_mode()
    written: list[str] = []
    trace_ids: list[str] = []

    conn = connect_ledger(execution_ledger_db_path)
    stub_migration: dict[str, Any] = {"ok": True, "updated": 0}
    policy_slot = policy_slot_early
    try:
        ensure_execution_ledger_schema(conn)
        stub_migration = _migrate_anna_parallel_stub_rows_to_paper(
            conn, market_db_path=market_data_db_path
        )
        sync_strategy_registry_from_catalog(conn)
        policy_slot = get_baseline_jupiter_policy_slot(conn)
    finally:
        conn.close()

    use_v3 = policy_slot == BASELINE_POLICY_SLOT_JUP_V3
    sm = signal_mode_for_baseline_policy_slot(policy_slot)
    if use_v3:
        sig = evaluate_sean_jupiter_baseline_v3(
            bars_asc=bars_asc,
            training_state=load_state(),
            ledger_db_path=execution_ledger_db_path,
        )
    else:
        sig = evaluate_sean_jupiter_baseline_v1(
            bars_asc=bars_asc,
            training_state=load_state(),
            ledger_db_path=execution_ledger_db_path,
        )
    if not sig.trade:
        return {
            "ok": True,
            "no_trade": True,
            "market_event_id": mid,
            "reason_code": sig.reason_code,
            "signal_mode": sm,
            "baseline_jupiter_policy_slot": policy_slot,
            "features": sig.features,
            "strategies": strategies,
            "parallel_mode": mode,
            "trades_written": 0,
            "trade_ids": [],
            "trace_ids": [],
            "stub_migration": stub_migration,
        }

    ctx = {
        **base_ctx,
        "parallel_signal": {
            "signal_mode": sm,
            "baseline_jupiter_policy_slot": policy_slot,
            "reason_code": sig.reason_code,
            "side": sig.side,
            "features": sig.features,
        },
    }

    for sid in strategies:
        if sid == RESERVED_STRATEGY_BASELINE:
            continue
        tid = _trade_id_for(sid, mid)
        try:
            if mode == "paper":
                out = persist_parallel_anna_paper_trade_with_trace(
                    market_event_id=mid,
                    strategy_id=sid,
                    bar=bar,
                    trade_id=tid,
                    side=str(sig.side),
                    signal_reason_code=str(sig.reason_code or ""),
                    context_snapshot={**ctx, "parallel_mode": "paper"},
                    notes=(
                        "parallel_runner economic paper — Sean Jupiter baseline signal "
                        f"({policy_slot}); open→close {sig.side}, size 1"
                    ),
                    db_path=execution_ledger_db_path,
                )
            else:
                result, stub_pnl = _stub_pnl_for_strategy(sid, mid)
                out = persist_parallel_anna_stub_trade_with_trace(
                    market_event_id=mid,
                    strategy_id=sid,
                    bar=bar,
                    stub_result=result,
                    stub_pnl_usd=stub_pnl,
                    trade_id=tid,
                    context_snapshot={
                        "synthetic": True,
                        "stub_result": result,
                        "stub_pnl_usd": stub_pnl,
                        **ctx,
                    },
                    notes=f"parallel_stub synthetic classification={result} (pnl_usd not asserted)",
                    db_path=execution_ledger_db_path,
                )
            written.append(tid)
            trace_ids.append(str(out.get("trace_id") or ""))
        except sqlite3.IntegrityError:
            # Idempotent re-run for same strategy+market_event_id (fixed trade_id).
            pass

    return {
        "ok": True,
        "market_event_id": mid,
        "strategies": strategies,
        "parallel_mode": mode,
        "signal_mode": sm,
        "baseline_jupiter_policy_slot": policy_slot,
        "stub_migration": stub_migration,
        "trades_written": len(written),
        "trade_ids": written,
        "trace_ids": trace_ids,
    }


def _trade_id_for(strategy_id: str, market_event_id: str) -> str:
    h = hashlib.sha256(f"{strategy_id}|{market_event_id}|parallel_v1".encode()).hexdigest()[:24]
    return f"pt_{h}"
