"""
Aggregated operator dashboard payload: trade chain, sequential status, wallet subset, system mode.

Trade chain: horizontal event axis (columns) × vertical chains (baseline, Anna test, Anna strategy rows).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Operator-visible cadence (must match dashboard.html poll interval and docker-compose defaults).
DASHBOARD_CLIENT_POLL_INTERVAL_MS = 1500
SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT = 5
PYTH_STREAM_PROBE_INTERVAL_SEC_DEFAULT = 15


def _parse_iso_ts(ts: str | None) -> datetime | None:
    if not ts or not str(ts).strip():
        return None
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _pyth_probe_snapshot(repo: Path) -> dict[str, Any]:
    p = repo / "docs" / "working" / "artifacts" / "pyth_stream_status.json"
    out: dict[str, Any] = {"status": None, "last_event_at": None, "age_seconds": None, "reason_code": None}
    if not p.is_file():
        out["reason_code"] = "pyth_artifact_missing"
        return out
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        out["reason_code"] = "pyth_artifact_bad_json"
        return out
    if not isinstance(raw, dict):
        return out
    out["status"] = raw.get("status") or raw.get("stream_state")
    out["reason_code"] = raw.get("reason_code")
    lu = raw.get("last_event_at") or raw.get("updated_at")
    out["last_event_at"] = lu
    dt = _parse_iso_ts(str(lu) if lu else None)
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        out["age_seconds"] = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    return out


def _sequential_tick_staleness(
    *,
    ui_state: str,
    events_remaining: int,
    last_tick_at: str | None,
    now: datetime,
) -> dict[str, Any]:
    """
    Operator-facing: distinguish live advancing vs running-but-stalled.
    Thresholds: degraded >45s, stalled >90s with queue > 0.
    """
    if ui_state != "running":
        return {
            "level": "not_running",
            "label": "IDLE",
            "detail": "Sequential learning is not in running state.",
        }
    if events_remaining <= 0:
        return {
            "level": "queue_empty",
            "label": "RUNNING · IDLE QUEUE",
            "detail": "No events left in file — last tick may not advance until new events.",
        }
    dt = _parse_iso_ts(last_tick_at)
    if dt is None:
        return {
            "level": "unknown",
            "label": "RUNNING · NO TICK YET",
            "detail": "Queue has events but no last_tick_at — wait for first tick.",
        }
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = max(0, int((now - dt).total_seconds()))
    if age > 90:
        return {
            "level": "stalled",
            "label": "STALLED",
            "detail": f"Last sequential tick was {age}s ago with {events_remaining} events still queued — check tick sidecar or API.",
        }
    if age > 45:
        return {
            "level": "degraded",
            "label": "LIVE (SLOW)",
            "detail": f"Last tick {age}s ago — expect ~{SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT}s when sidecar is up.",
        }
    return {
        "level": "live",
        "label": "LIVE",
        "detail": f"Last tick {age}s ago · {events_remaining} events remaining in queue.",
    }

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    connect_ledger,
    default_execution_ledger_path,
    ensure_execution_ledger_schema,
)
from modules.anna_training.quantitative_evaluation_layer.constants import (
    LIFECYCLE_CANDIDATE,
    LIFECYCLE_EXPERIMENT,
    LIFECYCLE_PROMOTED,
    LIFECYCLE_PROMOTION_READY,
    LIFECYCLE_TEST,
    LIFECYCLE_VALIDATED_STRATEGY,
)
from modules.anna_training.sequential_engine.mae_v1 import compute_mae_usd_v1

_MARKET_DB: Path | None = None


def _market_db_path() -> Path | None:
    global _MARKET_DB
    if _MARKET_DB is not None:
        return _MARKET_DB if _MARKET_DB.is_file() else None
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or os.environ.get("BLACKBOX_MARKET_DATA_DB") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        _MARKET_DB = p
        return p if p.is_file() else None
    repo = Path(__file__).resolve().parents[2]
    for candidate in (
        repo / "data" / "sqlite" / "market_data.db",
        repo / "data" / "sqlite" / "market_data.sqlite",
    ):
        if candidate.is_file():
            _MARKET_DB = candidate
            return candidate
    return None


def _outcome_from_pnl(pnl: float | None, *, mode: str) -> str:
    m = (mode or "").strip().lower()
    if m == "paper_stub":
        return "STUB"
    if pnl is None:
        return "—"
    try:
        p = float(pnl)
    except (TypeError, ValueError):
        return "—"
    if p > 1e-9:
        return "WIN"
    if p < -1e-9:
        return "LOSS"
    return "FLAT"


def _notional_usd(entry_price: float | None, size: float | None) -> float | None:
    if entry_price is None or size is None:
        return None
    try:
        ep = float(entry_price)
        sz = float(size)
    except (TypeError, ValueError):
        return None
    if ep != ep or sz != sz or sz <= 0:
        return None
    return round(ep * sz, 4)


def _compact_cell(
    row: dict[str, Any] | None,
    *,
    market_db_path: Path | None,
) -> dict[str, Any]:
    if not row:
        return {
            "empty": True,
            "market_event_id": None,
            "trade_id": None,
            "entry": None,
            "exit": None,
            "size": None,
            "notional_usd_approx": None,
            "pnl_usd": None,
            "mae_usd": None,
            "outcome": "—",
            "mode": None,
        }
    mode = str(row.get("mode") or "")
    pnl = row.get("pnl_usd")
    pnl_f = float(pnl) if pnl is not None else None
    sym = str(row.get("symbol") or "").strip()
    mae_val: float | None = None
    if sym and market_db_path and market_db_path.is_file():
        mae_val, _ = compute_mae_usd_v1(
            canonical_symbol=sym,
            side=row.get("side"),
            entry_price=row.get("entry_price"),
            size=row.get("size"),
            entry_time=row.get("entry_time"),
            exit_time=row.get("exit_time"),
            market_db_path=market_db_path,
        )
    return {
        "empty": False,
        "market_event_id": row.get("market_event_id"),
        "trade_id": row.get("trade_id"),
        "entry": row.get("entry_price"),
        "exit": row.get("exit_price"),
        "entry_time": row.get("entry_time"),
        "exit_time": row.get("exit_time"),
        "size": row.get("size"),
        "notional_usd_approx": _notional_usd(row.get("entry_price"), row.get("size")),
        "pnl_usd": pnl_f,
        "mae_usd": round(mae_val, 6) if mae_val is not None else None,
        "outcome": _outcome_from_pnl(pnl_f, mode=mode),
        "mode": mode,
    }


def _fetch_trade(
    conn: Any,
    market_event_id: str,
    *,
    lane: str,
    strategy_id: str,
) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
               side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
               pnl_usd, context_snapshot_json, notes, trace_id, created_at_utc
        FROM execution_trades
        WHERE market_event_id = ? AND lane = ? AND strategy_id = ?
        ORDER BY created_at_utc DESC, trade_id DESC
        LIMIT 1
        """,
        (market_event_id.strip(), lane.strip().lower(), strategy_id.strip()),
    )
    r = cur.fetchone()
    if not r:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, r))


def _distinct_event_axis(conn: Any, *, limit: int) -> list[str]:
    """Most recent ``limit`` distinct market_event_ids; returned oldest→newest (left→right)."""
    lim = max(4, min(48, int(limit)))
    cur = conn.execute(
        """
        SELECT market_event_id, MAX(created_at_utc) AS mx
        FROM execution_trades
        GROUP BY market_event_id
        ORDER BY mx DESC
        LIMIT ?
        """,
        (lim,),
    )
    mids = [str(r[0]) for r in cur.fetchall() if r and r[0]]
    return list(reversed(mids))


def _ledger_has_live_anna(conn: Any) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM execution_trades
        WHERE lane = 'anna' AND mode = 'live' LIMIT 1
        """
    ).fetchone()
    return bool(row)


def _ledger_lane_mode_summary(conn: Any) -> dict[str, Any]:
    """Baseline / Anna execution modes observed in ledger (capital-risk display)."""
    baseline_modes: list[str] = []
    anna_modes: list[str] = []
    try:
        cur = conn.execute(
            "SELECT DISTINCT mode FROM execution_trades WHERE lane = 'baseline' ORDER BY mode"
        )
        baseline_modes = [str(r[0]) for r in cur.fetchall() if r and r[0]]
    except Exception:
        pass
    try:
        cur = conn.execute(
            "SELECT DISTINCT mode FROM execution_trades WHERE lane = 'anna' ORDER BY mode"
        )
        anna_modes = [str(r[0]) for r in cur.fetchall() if r and r[0]]
    except Exception:
        pass

    def _disp(modes: list[str], lane: str) -> str:
        if not modes:
            return "paper_only" if lane == "anna" else "none"
        economic = [m for m in modes if m in ("live", "paper")]
        if lane == "baseline":
            if "live" in economic and "paper" in economic:
                return "mixed"
            if "live" in economic:
                return "live"
            if "paper" in economic:
                return "paper"
            return "stub" if "paper_stub" in modes else "mixed"
        # anna
        if "live" in economic:
            return "live_present"
        return "paper_only"

    return {
        "baseline_modes_observed": baseline_modes,
        "anna_modes_observed": anna_modes,
        "baseline_display": _disp(baseline_modes, "baseline"),
        "anna_display": _disp(anna_modes, "anna"),
    }


def _compact_last_decision(row: dict[str, Any] | None) -> str:
    if not row:
        return "—"
    for k in ("decision", "sprt_decision", "outcome", "status", "reason_code"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()[:100]
    tid = row.get("test_id") or row.get("strategy_id")
    if tid:
        return str(tid)[:80]
    return str(row)[:100]


def _strategy_buckets(conn: Any) -> tuple[list[str], list[str], str | None]:
    """
    Returns (test_strategy_ids, strategy_row_ids, note).
    Test = lifecycle in {test, experiment} OR listed in active survival tests.
    Strategy row = candidate / validated / promotion_ready / promoted.
    """
    survival: set[str] = set()
    try:
        cur = conn.execute(
            "SELECT strategy_id FROM anna_survival_tests WHERE status = 'active'"
        )
        survival = {str(r[0]) for r in cur.fetchall() if r and r[0]}
    except Exception:
        pass

    test_lc = frozenset({LIFECYCLE_TEST, LIFECYCLE_EXPERIMENT})
    strat_lc = frozenset(
        {
            LIFECYCLE_CANDIDATE,
            LIFECYCLE_VALIDATED_STRATEGY,
            LIFECYCLE_PROMOTION_READY,
            LIFECYCLE_PROMOTED,
        }
    )

    tests: list[str] = []
    strats: list[str] = []
    try:
        cur = conn.execute(
            """
            SELECT strategy_id, lifecycle_state FROM strategy_registry
            WHERE strategy_id != ?
            ORDER BY strategy_id ASC
            """,
            (RESERVED_STRATEGY_BASELINE,),
        )
        for sid, lc in cur.fetchall():
            s = str(sid).strip()
            lc_s = str(lc or LIFECYCLE_EXPERIMENT)
            if s in survival or lc_s in test_lc:
                tests.append(s)
            elif lc_s in strat_lc:
                strats.append(s)
    except Exception:
        pass

    tests = sorted(set(tests))[:4]
    strats = sorted(set(strats))[:4]
    note = None
    if not tests and not strats:
        note = "No Anna strategies in registry with test/strategy lifecycles — baseline row only until strategies are registered."
    return tests, strats, note


def build_trade_chain_payload(
    *,
    db_path: Path | None = None,
    max_events: int = 24,
    market_db_path: Path | None = None,
) -> dict[str, Any]:
    """Horizontal chains × vertical event axis from execution ledger."""
    db_path = db_path or default_execution_ledger_path()
    mpath = market_db_path if market_db_path is not None else _market_db_path()

    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        event_axis = _distinct_event_axis(conn, limit=max_events)
        tests, strats, note = _strategy_buckets(conn)

        row_defs: list[dict[str, Any]] = [
            {
                "chain_kind": "baseline",
                "label": "Baseline chain",
                "lane": "baseline",
                "strategy_id": RESERVED_STRATEGY_BASELINE,
                "account_note": "One account model per row; mode shown per cell.",
            }
        ]
        for sid in tests:
            row_defs.append(
                {
                    "chain_kind": "anna_test",
                    "label": f"Anna test · {sid}",
                    "lane": "anna",
                    "strategy_id": sid,
                    "account_note": "Anna test / experiment / survival-active lane",
                }
            )
        for sid in strats:
            row_defs.append(
                {
                    "chain_kind": "anna_strategy",
                    "label": f"Anna strategy · {sid}",
                    "lane": "anna",
                    "strategy_id": sid,
                    "account_note": "Candidate / validated / promotion lane",
                }
            )

        rows_out: list[dict[str, Any]] = []
        for rd in row_defs:
            cells: dict[str, Any] = {}
            for mid in event_axis:
                tr = _fetch_trade(conn, mid, lane=rd["lane"], strategy_id=rd["strategy_id"])
                cells[mid] = _compact_cell(tr, market_db_path=mpath)
            rows_out.append(
                {
                    **rd,
                    "cells": cells,
                }
            )
    finally:
        conn.close()

    return {
        "schema": "blackbox_trade_chain_v1",
        "ledger_path": str(db_path),
        "market_db_path": str(mpath) if mpath else None,
        "event_axis": event_axis,
        "event_axis_note": "Columns are distinct market_event_id values (recent window, oldest left → newest right).",
        "strategy_selection_note": note,
        "rows": rows_out,
    }


def _wallet_subset(full: dict[str, Any] | None) -> dict[str, Any]:
    if not full:
        return {"ok": False, "detail": "wallet_unavailable"}
    sig = full.get("signing_proof")
    return {
        "wallet_connected": bool(full.get("wallet_connected")),
        "public_address": full.get("public_address"),
        "balance_sol": full.get("balance_sol"),
        "balance_usd_approx": full.get("balance_usd_approx"),
        "solana_rpc_ok": bool((full.get("solana_rpc") or {}).get("ok")),
        "jupiter_quote_ok": bool((full.get("jupiter_quote_sample") or {}).get("ok")),
        "live_trading_blocked": bool(full.get("live_trading_blocked")),
        "signing_ok": bool(isinstance(sig, dict) and sig.get("ok")),
    }


def _system_mode_label(
    *,
    wallet: dict[str, Any] | None,
    ledger_has_live_anna: bool,
) -> dict[str, Any]:
    blocked = bool((wallet or {}).get("live_trading_blocked"))
    if blocked:
        return {
            "label": "PAPER",
            "reason": "Live trading blocked by policy until governance and wallet/Jupiter proof are satisfied.",
        }
    if ledger_has_live_anna:
        return {
            "label": "LIVE",
            "reason": "Execution ledger contains Anna lane rows with mode=live.",
        }
    return {
        "label": "PAPER",
        "reason": "No live Anna ledger rows; operational default is paper.",
    }


def build_dashboard_bundle(
    *,
    db_path: Path | None = None,
    max_events: int = 24,
) -> dict[str, Any]:
    """Single JSON for /api/v1/dashboard/bundle — operator surface."""
    tid = uuid.uuid4().hex
    db_path = db_path or default_execution_ledger_path()

    wallet_full: dict[str, Any] | None = None
    try:
        from modules.wallet import build_wallet_status_payload

        wallet_full = build_wallet_status_payload()
    except Exception:
        wallet_full = None

    wallet = _wallet_subset(wallet_full)

    try:
        from modules.anna_training.sequential_engine.ui_control import build_operator_status

        seq = build_operator_status()
    except Exception as e:
        seq = {"schema": "sequential_operator_status_v1", "ui_state": "unknown", "detail": str(e)[:200]}

    ledger_live = False
    capital_modes: dict[str, Any] = {
        "baseline_modes_observed": [],
        "anna_modes_observed": [],
        "baseline_display": "none",
        "anna_display": "paper_only",
    }
    try:
        conn = connect_ledger(db_path)
        try:
            ensure_execution_ledger_schema(conn)
            ledger_live = _ledger_has_live_anna(conn)
            capital_modes = _ledger_lane_mode_summary(conn)
        finally:
            conn.close()
    except Exception:
        pass

    mode = _system_mode_label(wallet=wallet_full, ledger_has_live_anna=ledger_live)

    tc = build_trade_chain_payload(db_path=db_path, max_events=max_events)

    ui_state = str((seq or {}).get("ui_state") or "idle")
    ev_rem = 0
    try:
        total = int((seq or {}).get("events_total_lines") or 0)
        cur = int((seq or {}).get("events_cursor_line") or 0)
        ev_rem = max(0, total - cur)
    except (TypeError, ValueError):
        pass

    learning_active = ui_state == "running"
    tick_banner = None
    if ui_state == "running" and ev_rem > 0:
        tick_banner = (
            f"Sequential learning advances via batch ticks (~every {SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT}s "
            "when the `sequential-tick` sidecar is running) or manual Tick / POST tick."
        )
    elif ui_state == "running" and ev_rem == 0:
        tick_banner = "Running — event queue empty (end of file or cursor at end)."

    now_utc = datetime.now(timezone.utc)
    pyth_snap = _pyth_probe_snapshot(_REPO_ROOT)
    tick_stale = _sequential_tick_staleness(
        ui_state=ui_state,
        events_remaining=ev_rem,
        last_tick_at=str((seq or {}).get("last_tick_at") or "") or None,
        now=now_utc,
    )
    liveness: dict[str, Any] = {
        "bundle_generated_at_utc": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "methodology_one_liner": (
            "Dashboard: REST poll of aggregated bundle; sequential: discrete batch ticks over a cursor; "
            "market: Hermes price probe JSON artifacts — not a sub-second order-book stream."
        ),
        "update_model": {
            "dashboard_ui": "poll_driven",
            "dashboard_poll_interval_ms": DASHBOARD_CLIENT_POLL_INTERVAL_MS,
            "bundle_source": "GET /api/v1/dashboard/bundle (server builds snapshot each request)",
            "sequential_engine": "tick_driven_batch",
            "sequential_tick_interval_sec_expected": SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT,
            "market_price_probe": "pyth_stream_probe Hermes HTTP",
            "pyth_probe_interval_sec_default": PYTH_STREAM_PROBE_INTERVAL_SEC_DEFAULT,
        },
        "operator_signals": {
            "sequential_events_processed_total": (seq or {}).get("events_processed_total"),
            "sequential_events_remaining_in_queue": ev_rem,
            "sequential_last_tick_at": (seq or {}).get("last_tick_at"),
            "last_processed_market_event_id": (seq or {}).get("last_processed_market_event_id"),
            "pyth_status": pyth_snap.get("status"),
            "pyth_last_event_at": pyth_snap.get("last_event_at"),
            "pyth_age_seconds": pyth_snap.get("age_seconds"),
            "tick_staleness": tick_stale,
        },
        "not_exchange_tick_stream": (
            "This dashboard is not a live order-book or millisecond tape. "
            "Liveness is: (1) bundle timestamp advancing every poll, (2) sequential last_tick_at advancing while queue>0, "
            "(3) Pyth probe age staying bounded, (4) STALLED label if ticks stop while queue remains."
        ),
    }

    last_dec = (seq or {}).get("last_decision_row")
    last_dec_s = None
    if isinstance(last_dec, dict):
        last_dec_s = json.dumps(last_dec, default=str)[:800]
    elif last_dec is not None:
        last_dec_s = str(last_dec)[:800]
    last_dec_banner = _compact_last_decision(last_dec if isinstance(last_dec, dict) else None)

    sprt = (seq or {}).get("last_sprt_decision")
    if sprt is None and isinstance((seq or {}).get("last_tick_summary"), dict):
        sprt = ((seq or {}).get("last_tick_summary") or {}).get("last_sprt")

    live_policy_blocked = bool(wallet.get("live_trading_blocked"))

    return {
        "schema": "blackbox_dashboard_bundle_v1",
        "trace_id": tid,
        "banner": {
            "ui_state": ui_state.upper(),
            "mode_label": str((mode or {}).get("label") or "PAPER"),
            "last_decision_compact": last_dec_banner,
            "last_processed_market_event_id": (seq or {}).get("last_processed_market_event_id"),
        },
        "capital_modes": capital_modes,
        "live_execution": {
            "live_trading_blocked_by_policy": live_policy_blocked,
            "ledger_anna_has_live_rows": ledger_live,
            "anna_lane_hint": "paper_only_until_unlocked" if live_policy_blocked else str(capital_modes.get("anna_display") or ""),
        },
        "operational_boundary": {
            "what_runs_now": [
                "UI/API (this dashboard, /api/v1/*)",
                "Sequential learning engine when ui_state=running and Tick advances the cursor",
                "Wallet status probe (RPC, optional Jupiter quote sample, signing proof script)",
            ],
            "shadow_only": [
                "Strategy evaluation overlays vs baseline (QEL) when ledger rows exist — not separate execution",
            ],
            "paper_only": [
                "Anna training execution ledger defaults to paper unless rows are explicitly mode=live",
                "Live trading remains blocked until governance clears wallet + Jupiter path",
            ],
            "not_yet_automated": [
                "Jupiter swap transaction submission from this dashboard",
                "Continuous event ingestion without Tick",
                "Drift/Jupiter perp bot — separate trading_core runtime",
            ],
        },
        "system_mode": mode,
        "wallet": wallet,
        "sequential": seq,
        "learning_summary": {
            "ui_state": ui_state,
            "learning_active": learning_active,
            "events_remaining_in_queue": ev_rem,
            "last_processed_market_event_id": (seq or {}).get("last_processed_market_event_id"),
            "last_tick_at": (seq or {}).get("last_tick_at"),
            "last_error": (seq or {}).get("last_error"),
            "sprt_or_compact": sprt,
            "last_decision_compact": last_dec_s,
            "tick_ux_banner": tick_banner,
            "tick_required": ui_state == "running" and ev_rem > 0,
            "events_processed_total": (seq or {}).get("events_processed_total"),
        },
        "trade_chain": tc,
        "liveness": liveness,
    }
