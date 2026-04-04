"""Aggregate JSON for GET /api/v1/anna/market-event-view — event-centric operator surface."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    default_execution_ledger_path,
    query_trades_by_market_event_id,
)

_REPO = Path(__file__).resolve().parents[2]
_RT = _REPO / "scripts" / "runtime"
if str(_RT) not in sys.path:
    sys.path.insert(0, str(_RT))

from _paths import default_market_data_path  # noqa: E402
from market_data.store import connect_market_db, ensure_market_schema, fetch_bar_by_market_event_id, latest_stored_bars  # noqa: E402


def _ledger_path() -> Path:
    raw = os.environ.get("BLACKBOX_EXECUTION_LEDGER_PATH") or ""
    return Path(raw).expanduser() if raw.strip() else default_execution_ledger_path()


def _market_db_path() -> Path:
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or "").strip()
    return Path(raw).expanduser() if raw else default_market_data_path()


def _parse_ctx(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("context_snapshot_json")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        return {}


def _result_for_trade(row: dict[str, Any]) -> dict[str, Any]:
    mode = (row.get("mode") or "").strip().lower()
    ctx = _parse_ctx(row)
    if mode == "paper_stub":
        stub = ctx.get("stub_result")
        return {
            "pnl_asserted": False,
            "economic_pnl_usd": None,
            "classification": str(stub) if stub is not None else None,
            "stub_classification": stub,
            "stub_pnl_usd": ctx.get("stub_pnl_usd"),
        }
    pnl = row.get("pnl_usd")
    if pnl is None:
        cls = None
    else:
        p = float(pnl)
        if p > 1e-9:
            cls = "won"
        elif p < -1e-9:
            cls = "lost"
        else:
            cls = "breakeven"
    return {
        "pnl_asserted": True,
        "economic_pnl_usd": float(pnl) if pnl is not None else None,
        "classification": cls,
        "stub_classification": None,
        "stub_pnl_usd": None,
    }


def _dedupe_traces(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for t in traces:
        tid = str(t.get("trace_id") or "")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append(t)
    return out


def _markers_from_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for row in trades:
        tid = str(row.get("trade_id") or "")
        trace_id = row.get("trace_id")
        mode = str(row.get("mode") or "")
        lane = str(row.get("lane") or "")
        sid = str(row.get("strategy_id") or "")
        et = row.get("entry_time")
        xt = row.get("exit_time")
        ep = row.get("entry_price")
        xp = row.get("exit_price")
        if et:
            markers.append(
                {
                    "kind": "entry",
                    "timestamp_utc": et,
                    "price": float(ep) if ep is not None else None,
                    "lane": lane,
                    "strategy_id": sid,
                    "trade_id": tid,
                    "trace_id": trace_id,
                    "mode": mode,
                }
            )
        if xt:
            markers.append(
                {
                    "kind": "exit",
                    "timestamp_utc": xt,
                    "price": float(xp) if xp is not None else None,
                    "lane": lane,
                    "strategy_id": sid,
                    "trade_id": tid,
                    "trace_id": trace_id,
                    "mode": mode,
                }
            )
    return markers


def _display_palette() -> tuple[list[str], list[str]]:
    """Stable colors: baseline blue, Anna purple family."""
    base = "#4a9eff"
    anna = ["#a855f7", "#c084fc", "#7c3aed", "#e879f9", "#9333ea", "#6366f1"]
    tags = ["BASE", "A1", "A2", "A3", "A4", "A5", "A6"]
    return [base] + anna, tags


def _color_for_strategy(strategy_id: str, lane: str, anna_index: int) -> dict[str, str]:
    colors, tags = _display_palette()
    if lane == "baseline" or strategy_id == RESERVED_STRATEGY_BASELINE:
        return {"color": colors[0], "tag": tags[0]}
    h = hashlib.sha256(strategy_id.encode()).hexdigest()
    idx = int(h[:8], 16) % (len(colors) - 1)
    return {"color": colors[1 + idx], "tag": tags[1 + (anna_index % (len(tags) - 1))]}


def build_strategy_catalog_response() -> dict[str, Any]:
    from modules.anna_training.strategy_catalog import load_strategy_catalog

    rows = []
    rows.append(
        {
            "strategy_id": RESERVED_STRATEGY_BASELINE,
            "title": "Sean baseline (reserved)",
            "display": _color_for_strategy(RESERVED_STRATEGY_BASELINE, "baseline", 0),
        }
    )
    anna_i = 0
    for s in load_strategy_catalog():
        sid = str(s.get("id") or "").strip()
        if not sid or sid == RESERVED_STRATEGY_BASELINE:
            continue
        rows.append(
            {
                "strategy_id": sid,
                "title": str(s.get("title") or sid)[:500],
                "display": _color_for_strategy(sid, "anna", anna_i),
            }
        )
        anna_i += 1
    return {"schema": "anna_strategy_catalog_v1", "ok": True, "strategies": rows}


def _mode_allowed(mode: str, include_modes: set[str] | None, exclude_modes: set[str]) -> bool:
    m = (mode or "").strip().lower()
    if m in exclude_modes:
        return False
    if include_modes is not None and m not in include_modes:
        return False
    return True


def _lane_allowed(lane: str, lane_filter: str | None) -> bool:
    if not lane_filter:
        return True
    return (lane or "").strip().lower() == lane_filter.strip().lower()


def build_market_event_view(qs: dict[str, list[str]]) -> dict[str, Any]:
    from modules.anna_training.decision_trace import query_traces_by_market_event_id

    def _one(name: str) -> str | None:
        v = (qs.get(name) or [None])[0]
        return (str(v) if v is not None else "").strip() or None

    mid = _one("market_event_id")
    if not mid:
        return {
            "schema": "anna_market_event_view_v1",
            "ok": False,
            "error": "missing_market_event_id",
            "detail": "Query parameter market_event_id is required.",
        }

    modes_raw = _one("modes")
    exclude_raw = _one("exclude_modes")
    lane_filter = _one("lane")

    include_modes: set[str] | None = None
    if modes_raw:
        include_modes = {x.strip().lower() for x in modes_raw.split(",") if x.strip()}
    exclude_modes = {x.strip().lower() for x in (exclude_raw or "").split(",") if x.strip()}

    ledger_path = _ledger_path()
    market_path = _market_db_path()

    # Bar + history
    event_block: dict[str, Any] = {"symbol": None, "timeframe": None, "bar": None}
    history_bars: list[dict[str, Any]] = []
    try:
        conn_m = connect_market_db(market_path)
        try:
            ensure_market_schema(conn_m, _REPO)
            bar = fetch_bar_by_market_event_id(conn_m, mid)
            if bar:
                event_block["symbol"] = bar.get("canonical_symbol")
                event_block["timeframe"] = bar.get("timeframe")
                event_block["bar"] = bar
                sym = str(bar.get("canonical_symbol") or "")
                if sym:
                    hist = latest_stored_bars(conn_m, sym, limit=48)
                    for h in hist:
                        history_bars.append(
                            {
                                "candle_open_utc": h.get("candle_open_utc"),
                                "open": h.get("open"),
                                "high": h.get("high"),
                                "low": h.get("low"),
                                "close": h.get("close"),
                                "market_event_id": h.get("market_event_id"),
                            }
                        )
        finally:
            conn_m.close()
    except Exception as e:  # noqa: BLE001
        return {
            "schema": "anna_market_event_view_v1",
            "ok": False,
            "error": "market_data_error",
            "detail": str(e),
            "market_event_id": mid,
        }

    # Trades + traces
    try:
        raw_trades = query_trades_by_market_event_id(mid, db_path=ledger_path)
    except Exception as e:  # noqa: BLE001
        return {
            "schema": "anna_market_event_view_v1",
            "ok": False,
            "error": "ledger_error",
            "detail": str(e),
            "market_event_id": mid,
        }

    all_trade_rows = [dict(r) for r in raw_trades]

    def _enrich_row(row: dict[str, Any]) -> dict[str, Any]:
        r = dict(row)
        ctx = _parse_ctx(r)
        r["context_snapshot"] = ctx
        r.pop("context_snapshot_json", None)
        r["result"] = _result_for_trade({**r, "context_snapshot": ctx})
        return r

    all_full: list[dict[str, Any]] = [_enrich_row(dict(x)) for x in all_trade_rows]

    baseline_row_unfiltered = next((x for x in all_full if str(x.get("lane")) == "baseline"), None)

    trades_enriched: list[dict[str, Any]] = []
    for row in all_full:
        mode = str(row.get("mode") or "")
        lane = str(row.get("lane") or "")
        if not _mode_allowed(mode, include_modes, exclude_modes):
            continue
        if not _lane_allowed(lane, lane_filter):
            continue
        trades_enriched.append(row)

    try:
        raw_traces = query_traces_by_market_event_id(mid, db_path=ledger_path)
    except Exception as e:  # noqa: BLE001
        return {
            "schema": "anna_market_event_view_v1",
            "ok": False,
            "error": "trace_query_error",
            "detail": str(e),
            "market_event_id": mid,
        }

    traces_f: list[dict[str, Any]] = []
    trade_ids_kept = {t.get("trade_id") for t in trades_enriched}
    for tr in _dedupe_traces(raw_traces):
        tid = tr.get("trade_id")
        mode = str(tr.get("mode") or "")
        lane = str(tr.get("lane") or "")
        if not tid or tid not in trade_ids_kept:
            continue
        if not _mode_allowed(mode, include_modes, exclude_modes):
            continue
        if not _lane_allowed(lane, lane_filter):
            continue
        traces_f.append(tr)

    markers = _markers_from_trades(trades_enriched)

    if baseline_row_unfiltered:
        br0 = baseline_row_unfiltered
        btid = br0.get("trace_id")
        baseline_slot = {
            "lane": "baseline",
            "strategy_id": RESERVED_STRATEGY_BASELINE,
            "state": "trade_recorded",
            "trade": {"trade_id": br0.get("trade_id"), "mode": br0.get("mode")},
            "trace": {"trace_id": btid} if btid else None,
            "reason_code": None,
            "detail": None,
        }
        baseline_row_for_table = br0
    else:
        baseline_slot = {
            "lane": "baseline",
            "strategy_id": RESERVED_STRATEGY_BASELINE,
            "state": "no_trade",
            "trade": None,
            "trace": None,
            "reason_code": "no_baseline_row_in_ledger",
            "detail": "No execution_trades row for lane=baseline for this market_event_id.",
        }
        baseline_row_for_table = None

    from modules.anna_training.strategy_catalog import load_strategy_catalog

    catalog_ids = [
        str(x.get("id") or "").strip()
        for x in load_strategy_catalog()
        if str(x.get("id") or "").strip() and str(x.get("id")) != RESERVED_STRATEGY_BASELINE
    ]
    anna_trade_sids = {
        str(t.get("strategy_id"))
        for t in all_full
        if str(t.get("lane")) == "anna" and t.get("strategy_id")
    }
    ordered_anna = list(dict.fromkeys(catalog_ids + sorted(anna_trade_sids)))

    strategy_slots: list[dict[str, Any]] = []
    strategy_slots.append(
        {
            "strategy_id": RESERVED_STRATEGY_BASELINE,
            "lane": "baseline",
            "display": _color_for_strategy(RESERVED_STRATEGY_BASELINE, "baseline", 0),
            "trade_id": baseline_row_unfiltered.get("trade_id") if baseline_row_unfiltered else None,
            "trace_id": baseline_row_unfiltered.get("trace_id") if baseline_row_unfiltered else None,
        }
    )
    for i, sid in enumerate(ordered_anna):
        match = next(
            (t for t in all_full if str(t.get("strategy_id")) == sid and str(t.get("lane")) == "anna"),
            None,
        )
        strategy_slots.append(
            {
                "strategy_id": sid,
                "lane": "anna",
                "display": _color_for_strategy(sid, "anna", i),
                "trade_id": match.get("trade_id") if match else None,
                "trace_id": match.get("trace_id") if match else None,
            }
        )

    strategy_rows: list[dict[str, Any]] = []
    for sl in strategy_slots:
        sid = sl["strategy_id"]
        lane = sl["lane"]
        if lane == "baseline" and sid == RESERVED_STRATEGY_BASELINE:
            if baseline_row_for_table:
                br = baseline_row_for_table
                strategy_rows.append(
                    {
                        "lane": lane,
                        "strategy_id": sid,
                        "mode": br.get("mode"),
                        "side": br.get("side"),
                        "entry_time": br.get("entry_time"),
                        "exit_time": br.get("exit_time"),
                        "entry_price": br.get("entry_price"),
                        "exit_price": br.get("exit_price"),
                        "result": br.get("result"),
                        "trade_id": br.get("trade_id"),
                        "trace_id": br.get("trace_id"),
                        "row_state": "trade_recorded",
                        "display": sl.get("display"),
                    }
                )
            else:
                strategy_rows.append(
                    {
                        "lane": lane,
                        "strategy_id": sid,
                        "mode": None,
                        "side": None,
                        "entry_time": None,
                        "exit_time": None,
                        "entry_price": None,
                        "exit_price": None,
                        "result": None,
                        "trade_id": None,
                        "trace_id": None,
                        "row_state": "no_trade",
                        "display": sl.get("display"),
                    }
                )
            continue

        match = next(
            (t for t in all_full if str(t.get("strategy_id")) == sid and str(t.get("lane")) == lane),
            None,
        )
        if match:
            strategy_rows.append(
                {
                    "lane": lane,
                    "strategy_id": sid,
                    "mode": match.get("mode"),
                    "side": match.get("side"),
                    "entry_time": match.get("entry_time"),
                    "exit_time": match.get("exit_time"),
                    "entry_price": match.get("entry_price"),
                    "exit_price": match.get("exit_price"),
                    "result": match.get("result"),
                    "trade_id": match.get("trade_id"),
                    "trace_id": match.get("trace_id"),
                    "row_state": "trade_recorded",
                    "display": sl.get("display"),
                }
            )
        else:
            strategy_rows.append(
                {
                    "lane": lane,
                    "strategy_id": sid,
                    "mode": None,
                    "side": None,
                    "entry_time": None,
                    "exit_time": None,
                    "entry_price": None,
                    "exit_price": None,
                    "result": None,
                    "trade_id": None,
                    "trace_id": None,
                    "row_state": "no_trade",
                    "display": sl.get("display"),
                }
            )

    context_by_trade: list[dict[str, Any]] = []
    for t in trades_enriched:
        ctx = t.get("context_snapshot") or {}
        if ctx:
            context_by_trade.append(
                {
                    "trade_id": t.get("trade_id"),
                    "strategy_id": t.get("strategy_id"),
                    "lane": t.get("lane"),
                    "snapshot": ctx,
                }
            )

    return {
        "schema": "anna_market_event_view_v1",
        "ok": True,
        "market_event_id": mid,
        "filters_applied": {
            "modes": sorted(include_modes) if include_modes else None,
            "exclude_modes": sorted(exclude_modes),
            "lane": lane_filter,
        },
        "ledger_path": str(ledger_path),
        "market_data_path": str(market_path),
        "event": event_block,
        "chart": {
            "markers": markers,
            "history_bars": history_bars,
            "event_market_event_id": mid,
        },
        "baseline_slot": baseline_slot,
        "strategy_slots": strategy_slots,
        "strategy_rows": strategy_rows,
        "trades": trades_enriched,
        "decision_traces": traces_f,
        "context_by_trade": context_by_trade,
    }
