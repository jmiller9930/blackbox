"""Export execution_trades (+ optional decision_traces join) to CSV — full entry → exit detail."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, default_execution_ledger_path, ensure_execution_ledger_schema

# Same column order as CSV / TUI (1 datetime 2 trade 3 entry 4 exit …).
TRADE_EXPORT_FIELDNAMES: tuple[str, ...] = (
    "datetime_utc",
    "trade_id",
    "entry",
    "exit",
    "market_event_id",
    "strategy_id",
    "lane",
    "mode",
    "symbol",
    "timeframe",
    "side",
    "entry_time",
    "entry_price",
    "size",
    "exit_time",
    "exit_price",
    "exit_reason",
    "pnl_usd",
    "mae_usd",
    "mae_exclusion_reason",
    "trace_id",
    "trace_timestamp_start_utc",
    "trace_timestamp_end_utc",
    "trace_decision_summary",
    "trace_memory_used",
    "trace_retrieved_memory_ids_json",
    "trace_steps_json",
    "context_snapshot_json",
    "notes",
    "schema_version",
    "created_at_utc",
)

# TUI-only column after ``datetime_utc`` (derived from ``pnl_usd``; not written to CSV).
TUI_WIN_LOSS_FIELD = "W/L"


def format_wl_from_pnl(pnl_usd: Any) -> str:
    """Win / loss / flat for dashboard TUI (front of row, after time)."""
    if pnl_usd is None:
        return "—"
    try:
        v = float(pnl_usd)
    except (TypeError, ValueError):
        return "—"
    if v > 1e-9:
        return "W"
    if v < -1e-9:
        return "L"
    return "flat"


def tui_ledger_column_order() -> tuple[str, ...]:
    """When → W/L → same fields as CSV (``trade_id`` … ``created_at_utc``)."""
    return (TRADE_EXPORT_FIELDNAMES[0], TUI_WIN_LOSS_FIELD) + TRADE_EXPORT_FIELDNAMES[1:]


def _fmt_entry(
    *,
    side: str | None,
    entry_time: str | None,
    entry_price: float | None,
    size: float | None,
) -> str:
    parts = [
        f"side={side or ''}",
        f"entry_time={entry_time or ''}",
        f"entry_price={entry_price}",
        f"size={size}",
    ]
    return " | ".join(parts)


def _fmt_exit(
    *,
    exit_time: str | None,
    exit_price: float | None,
    exit_reason: str | None,
    pnl_usd: float | None,
) -> str:
    parts = [
        f"exit_time={exit_time or ''}",
        f"exit_price={exit_price}",
        f"exit_reason={exit_reason or ''}",
        f"pnl_usd={pnl_usd}",
    ]
    return " | ".join(parts)


def fetch_trade_export_rows(
    *,
    db_path: Path | None = None,
    lane: str | None = None,
    strategy_id: str | None = None,
    limit: int | None = None,
    with_mae: bool = False,
) -> list[dict[str, Any]]:
    """
    Same rows as ``export_execution_trades_to_csv`` (for TUI / API).
    Newest first. Dict keys match ``TRADE_EXPORT_FIELDNAMES``.
    """
    db_path = db_path or default_execution_ledger_path()
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        wh: list[str] = []
        params: list[Any] = []
        if lane:
            wh.append("t.lane = ?")
            params.append(lane.strip().lower())
        if strategy_id:
            wh.append("t.strategy_id = ?")
            params.append(strategy_id.strip())
        where = (" WHERE " + " AND ".join(wh)) if wh else ""
        lim = f" LIMIT {int(limit)}" if limit is not None and limit > 0 else ""

        sql = f"""
        SELECT
          t.trade_id,
          t.strategy_id,
          t.lane,
          t.mode,
          t.market_event_id,
          t.symbol,
          t.timeframe,
          t.side,
          t.entry_time,
          t.entry_price,
          t.size,
          t.exit_time,
          t.exit_price,
          t.exit_reason,
          t.pnl_usd,
          t.context_snapshot_json,
          t.notes,
          t.trace_id,
          t.schema_version,
          t.created_at_utc,
          dt.timestamp_start_utc AS trace_timestamp_start_utc,
          dt.timestamp_end_utc AS trace_timestamp_end_utc,
          dt.decision_summary AS trace_decision_summary,
          dt.steps_json AS trace_steps_json,
          dt.memory_used AS trace_memory_used,
          dt.retrieved_memory_ids_json AS trace_retrieved_memory_ids_json
        FROM execution_trades t
        LEFT JOIN decision_traces dt ON dt.trace_id = t.trace_id
        {where}
        ORDER BY t.created_at_utc DESC, t.trade_id DESC
        {lim}
        """
        cur = conn.execute(sql, params)
        raw_rows = cur.fetchall()
        colnames = [d[0] for d in cur.description]
    finally:
        conn.close()

    mae_by_trade: dict[str, float | None] = {}
    mae_reason: dict[str, str | None] = {}
    if with_mae and raw_rows:
        from modules.anna_training.sequential_engine.mae_v1 import compute_mae_usd_v1

        market_db = os.environ.get("BLACKBOX_MARKET_DATA_DB") or str(
            Path(__file__).resolve().parents[2] / "data" / "sqlite" / "market_data.db"
        )
        mp = Path(market_db)
        for r in raw_rows:
            d = dict(zip(colnames, r))
            tid = str(d.get("trade_id") or "")
            if not tid:
                continue
            mae_val, excl = compute_mae_usd_v1(
                canonical_symbol=str(d.get("symbol") or ""),
                side=d.get("side"),
                entry_price=d.get("entry_price"),
                size=d.get("size"),
                entry_time=d.get("entry_time"),
                exit_time=d.get("exit_time"),
                market_db_path=mp if mp.is_file() else None,
            )
            mae_by_trade[tid] = round(mae_val, 6) if mae_val is not None else None
            mae_reason[tid] = excl

    fieldnames = list(TRADE_EXPORT_FIELDNAMES)
    out: list[dict[str, Any]] = []
    for r in raw_rows:
        d = dict(zip(colnames, r))
        tid = str(d.get("trade_id") or "")
        eb = _fmt_entry(
            side=d.get("side"),
            entry_time=d.get("entry_time"),
            entry_price=d.get("entry_price"),
            size=d.get("size"),
        )
        xb = _fmt_exit(
            exit_time=d.get("exit_time"),
            exit_price=d.get("exit_price"),
            exit_reason=d.get("exit_reason"),
            pnl_usd=d.get("pnl_usd"),
        )
        dt_u = (d.get("entry_time") or "").strip() or (d.get("created_at_utc") or "").strip() or ""
        out_row = {k: d.get(k) for k in fieldnames if k not in ("datetime_utc", "entry", "exit", "mae_usd", "mae_exclusion_reason")}
        out_row["datetime_utc"] = dt_u
        out_row["entry"] = eb
        out_row["exit"] = xb
        out_row["mae_usd"] = mae_by_trade.get(tid) if with_mae else ""
        out_row["mae_exclusion_reason"] = mae_reason.get(tid) if with_mae else ""
        for k in ("context_snapshot_json", "trace_steps_json", "trace_retrieved_memory_ids_json"):
            v = out_row.get(k)
            if v is not None and not isinstance(v, str):
                out_row[k] = json.dumps(v)
        out.append(out_row)
    return out


def export_execution_trades_to_csv(
    *,
    out_path: Path,
    db_path: Path | None = None,
    lane: str | None = None,
    strategy_id: str | None = None,
    limit: int | None = None,
    with_mae: bool = False,
) -> dict[str, Any]:
    """
    Write one CSV row per execution_trades row, newest first.

    Column order: ``datetime_utc`` → ``trade_id`` → ``entry`` → ``exit`` → details → trace → JSON.
    ``datetime_utc`` prefers ``entry_time``, else ``created_at_utc``.
    """
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    rows = fetch_trade_export_rows(
        db_path=db_path,
        lane=lane,
        strategy_id=strategy_id,
        limit=limit,
        with_mae=with_mae,
    )
    fieldnames = list(TRADE_EXPORT_FIELDNAMES)

    n = 0
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for out_row in rows:
            w.writerow(out_row)
            n += 1

    return {"ok": True, "path": str(p.resolve()), "rows_written": n, "with_mae": with_mae}


def default_export_csv_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(__file__).resolve().parents[2]
    d = root / "data" / "runtime" / "trade_exports"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"trades_export_{stamp}.csv"
