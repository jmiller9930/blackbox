"""
Phase 1 dataset builder — authoritative joins only (no alternate policy path).

Joins:
  - execution_trades (baseline lane, lifecycle exits)
  - context_snapshot_json → entry_market_event_id
  - policy_evaluations @ entry mid (same signal_mode as bridge)
  - market_bars_5m @ entry and exit mids
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    connect_ledger,
    ensure_execution_ledger_schema,
    fetch_policy_evaluation_for_market_event,
)
from modules.anna_training.learning_layer.label_specs import (
    WHIPSAW_LOOKAHEAD_BARS,
    beats_baseline_label,
    compute_whipsaw_flag,
    stopped_early_label,
    trade_success_label,
)
from modules.anna_training.learning_layer.schema import LEARNING_DATASET_SCHEMA_VERSION
DEFAULT_SIGNAL_MODE = "sean_jupiter_v1"


def _parse_ctx_entry_mid(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    v = d.get("entry_market_event_id")
    return str(v).strip() if v else None


def _fetch_bar(conn: sqlite3.Connection, mid: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT open, high, low, close, volume_base, candle_open_utc, market_event_id, canonical_symbol
        FROM market_bars_5m
        WHERE market_event_id = ?
        LIMIT 1
        """,
        (mid.strip(),),
    ).fetchone()
    if not row:
        return None
    return {
        "open": row[0],
        "high": row[1],
        "low": row[2],
        "close": row[3],
        "volume_base": row[4],
        "candle_open_utc": row[5],
        "market_event_id": row[6],
        "canonical_symbol": row[7],
    }


def _fetch_bars_after(
    conn: sqlite3.Connection,
    *,
    canonical_symbol: str,
    after_candle_open_utc: str,
    limit: int,
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT high, low, open, close, candle_open_utc, market_event_id
        FROM market_bars_5m
        WHERE canonical_symbol = ?
          AND candle_open_utc > ?
        ORDER BY candle_open_utc ASC
        LIMIT ?
        """,
        (canonical_symbol.strip(), after_candle_open_utc, max(0, int(limit))),
    )
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        out.append(
            {
                "high": r[0],
                "low": r[1],
                "open": r[2],
                "close": r[3],
                "candle_open_utc": r[4],
                "market_event_id": r[5],
            }
        )
    return out


def build_phase1_dataset(
    *,
    ledger_db_path: Path | None = None,
    market_db_path: Path | None = None,
    signal_mode: str = DEFAULT_SIGNAL_MODE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Returns ``(rows, inventory)`` where ``inventory`` summarizes joins and drops.
    Only **Jupiter_2 lifecycle** economic rows: ``exit_reason`` in ``STOP_LOSS``, ``TAKE_PROFIT``.
    """
    inv: dict[str, Any] = {
        "ledger_path": str(ledger_db_path) if ledger_db_path else "default",
        "market_path": str(market_db_path) if market_db_path else "default",
        "signal_mode": signal_mode,
        "exit_reason_filter": ("STOP_LOSS", "TAKE_PROFIT"),
    }
    from modules.anna_training.execution_ledger import default_execution_ledger_path
    from modules.anna_training.quantitative_evaluation_layer.ledger_cohort import (
        _default_market_db_path,
    )

    lp = ledger_db_path or default_execution_ledger_path()
    mp = market_db_path or _default_market_db_path()

    rows_out: list[dict[str, Any]] = []
    counts: dict[str, int] = {
        "trades_considered": 0,
        "missing_entry_mid": 0,
        "missing_entry_bar": 0,
        "missing_exit_bar": 0,
        "missing_policy": 0,
        "rows_ok": 0,
    }

    if not lp.is_file():
        inv["error"] = "ledger_missing"
        return [], inv
    if not mp.is_file():
        inv["error"] = "market_db_missing"
        return [], inv

    conn_l = connect_ledger(lp)
    conn_m = sqlite3.connect(f"file:{mp}?mode=ro", uri=True)
    try:
        ensure_execution_ledger_schema(conn_l)
        cur = conn_l.execute(
            """
            SELECT trade_id, market_event_id, symbol, timeframe, mode, side,
                   entry_price, exit_price, size, pnl_usd, exit_reason,
                   context_snapshot_json, created_at_utc
            FROM execution_trades
            WHERE lane = ? AND strategy_id = ?
              AND mode IN ('paper', 'live')
              AND exit_reason IN ('STOP_LOSS', 'TAKE_PROFIT')
            ORDER BY created_at_utc ASC
            """,
            (RESERVED_STRATEGY_BASELINE, RESERVED_STRATEGY_BASELINE),
        )
        for r in cur.fetchall():
            counts["trades_considered"] += 1
            trade_id = str(r[0])
            mid_exit = str(r[1])
            symbol = str(r[2] or "")
            timeframe = str(r[3] or "")
            mode = str(r[4] or "")
            side = r[5]
            entry_price, exit_price, size, pnl_usd, exit_reason = r[6], r[7], r[8], r[9], r[10]
            ctx_raw = r[11]
            created_at_utc = str(r[12]) if len(r) > 12 and r[12] else None

            entry_mid = _parse_ctx_entry_mid(str(ctx_raw) if ctx_raw else None)
            row_quality = "ok"
            if not entry_mid:
                counts["missing_entry_mid"] += 1
                row_quality = "missing_entry_mid"

            exit_bar = _fetch_bar(conn_m, mid_exit)
            if not exit_bar:
                counts["missing_exit_bar"] += 1
                if row_quality == "ok":
                    row_quality = "missing_exit_bar"

            entry_bar = _fetch_bar(conn_m, entry_mid) if entry_mid else None
            if entry_mid and not entry_bar:
                counts["missing_entry_bar"] += 1
                if row_quality == "ok":
                    row_quality = "missing_entry_bar"

            pol = None
            policy_json = None
            if entry_mid:
                pol = fetch_policy_evaluation_for_market_event(
                    conn_l,
                    entry_mid,
                    lane=RESERVED_STRATEGY_BASELINE,
                    strategy_id=RESERVED_STRATEGY_BASELINE,
                    signal_mode=signal_mode,
                )
                if pol:
                    policy_json = json.dumps(pol.get("features") or {}, sort_keys=True, default=str)
                else:
                    counts["missing_policy"] += 1
                    if row_quality == "ok":
                        row_quality = "missing_policy"

            bars_after: list[dict[str, Any]] = []
            if exit_bar and entry_bar and symbol:
                sym = str(exit_bar.get("canonical_symbol") or symbol)
                ac = exit_bar.get("candle_open_utc")
                if ac:
                    bars_after = _fetch_bars_after(
                        conn_m,
                        canonical_symbol=sym,
                        after_candle_open_utc=str(ac),
                        limit=WHIPSAW_LOOKAHEAD_BARS,
                    )

            ws = compute_whipsaw_flag(
                side=str(side) if side else None,
                entry_price=float(entry_price) if entry_price is not None else None,
                exit_reason=str(exit_reason) if exit_reason else None,
                bars_after_exit=bars_after,
            )

            rec = {
                "schema_version": LEARNING_DATASET_SCHEMA_VERSION,
                "created_at_utc": created_at_utc,
                "trade_id": trade_id,
                "market_event_id_exit": mid_exit,
                "market_event_id_entry": entry_mid,
                "symbol": symbol,
                "timeframe": timeframe,
                "mode": mode,
                "side": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "size": size,
                "pnl_usd": pnl_usd,
                "exit_reason": exit_reason,
                "entry_open": entry_bar["open"] if entry_bar else None,
                "entry_high": entry_bar["high"] if entry_bar else None,
                "entry_low": entry_bar["low"] if entry_bar else None,
                "entry_close": entry_bar["close"] if entry_bar else None,
                "entry_volume_base": entry_bar.get("volume_base") if entry_bar else None,
                "exit_open": exit_bar["open"] if exit_bar else None,
                "exit_high": exit_bar["high"] if exit_bar else None,
                "exit_low": exit_bar["low"] if exit_bar else None,
                "exit_close": exit_bar["close"] if exit_bar else None,
                "policy_features_json": policy_json,
                "trade_success": trade_success_label(exit_reason=str(exit_reason) if exit_reason else None),
                "stopped_early": stopped_early_label(exit_reason=str(exit_reason) if exit_reason else None),
                "beats_baseline": beats_baseline_label(pnl_usd=float(pnl_usd) if pnl_usd is not None else None),
                "whipsaw_flag": ws,
                "row_quality": row_quality,
            }
            if row_quality == "ok":
                counts["rows_ok"] += 1
            rows_out.append(rec)
    finally:
        conn_l.close()
        conn_m.close()

    inv["counts"] = counts
    inv["row_count"] = len(rows_out)
    return rows_out, inv


def row_to_csv_dict(rec: dict[str, Any]) -> dict[str, Any]:
    """Flatten booleans for CSV export if needed."""
    out = dict(rec)
    for k in ("trade_success", "stopped_early", "beats_baseline", "whipsaw_flag"):
        if k in out:
            out[k] = 1 if out[k] else 0
    return out
