"""
Compare Sean parity SQLite (klines-mini capture) to Blackbox JUPv3 truth:

- ``binance_strategy_bars_5m`` (OHLCV)
- ``policy_evaluations`` (``signal_mode=sean_jupiter_v3``)

Sean DB is written by ``vscode-test/binance-klines-mini/app.mjs`` when ``SQLITE_PATH`` is set.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from modules.anna_training.baseline_chain_validate import default_market_db_path
from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    SIGNAL_MODE_JUPITER_3,
    connect_ledger,
    default_execution_ledger_path,
    ensure_execution_ledger_schema,
    fetch_policy_evaluation_for_market_event,
)

OHLC_EPS = 1e-6


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_runtime_for_market_imports() -> None:
    rt = _repo_root() / "scripts" / "runtime"
    s = str(rt)
    import sys

    if s not in sys.path:
        sys.path.insert(0, s)


def fetch_binance_strategy_row(
    conn: sqlite3.Connection,
    market_event_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT candle_open_utc, open, high, low, close, volume_base_asset, quote_volume_usdt, market_event_id
        FROM binance_strategy_bars_5m
        WHERE market_event_id = ?
        LIMIT 1
        """,
        (market_event_id,),
    ).fetchone()
    if not row:
        return None
    keys = [
        "candle_open_utc",
        "open",
        "high",
        "low",
        "close",
        "volume_base_asset",
        "quote_volume_usdt",
        "market_event_id",
    ]
    return dict(zip(keys, row))


def load_sean_poll_rows(sean_db: Path) -> list[dict[str, Any]]:
    """Latest snapshot per ``market_event_id`` from ``sean_binance_kline_poll``."""
    conn = sqlite3.connect(f"file:{sean_db}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            """
            SELECT name FROM sqlite_master WHERE type='table' AND name='sean_binance_kline_poll'
            """
        )
        if cur.fetchone() is None:
            return []
        rows = conn.execute(
            """
            SELECT market_event_id, candle_open_ms, open_px, high_px, low_px, close_px, volume_base,
                   polled_at_utc, latency_ms
            FROM sean_binance_kline_poll
            WHERE id IN (
              SELECT MAX(id) FROM sean_binance_kline_poll GROUP BY market_event_id
            )
            ORDER BY candle_open_ms ASC
            """
        ).fetchall()
    finally:
        conn.close()
    keys = [
        "market_event_id",
        "candle_open_ms",
        "open_px",
        "high_px",
        "low_px",
        "close_px",
        "volume_base",
        "polled_at_utc",
        "latency_ms",
    ]
    return [dict(zip(keys, r)) for r in rows]


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def compare_sean_sqlite_to_blackbox(
    *,
    sean_sqlite_path: Path,
    market_db_path: Path | None = None,
    ledger_db_path: Path | None = None,
) -> dict[str, Any]:
    """
    For each latest Sean poll row per ``market_event_id``, compare OHLC to ``binance_strategy_bars_5m``
    and report policy row presence for ``sean_jupiter_v3``.
    """
    mpath = market_db_path or default_market_db_path()
    lpath = ledger_db_path or default_execution_ledger_path()
    sean_rows = load_sean_poll_rows(sean_sqlite_path)
    if not sean_rows:
        return {
            "schema": "jup_v3_parity_compare_v1",
            "ok": True,
            "error": None,
            "summary": {"sean_rows": 0, "ohlc_match": 0, "ohlc_mismatch": 0, "blackbox_bar_missing": 0, "policy_present": 0},
            "rows": [],
            "plain_english": "No rows in sean_binance_kline_poll (empty or missing table).",
        }

    if not mpath or not mpath.is_file():
        return {
            "schema": "jup_v3_parity_compare_v1",
            "ok": False,
            "error": "market_db_missing",
            "summary": {},
            "rows": [],
            "plain_english": "BLACKBOX market_data.db not found — set BLACKBOX_MARKET_DATA_PATH or path.",
        }

    _ensure_runtime_for_market_imports()
    from market_data.store import connect_market_db, ensure_market_schema

    mconn = connect_market_db(mpath)
    ensure_market_schema(mconn)

    lconn: sqlite3.Connection | None = None
    if lpath.is_file():
        lconn = connect_ledger(lpath)
        ensure_execution_ledger_schema(lconn)

    out_rows: list[dict[str, Any]] = []
    ohlc_match = ohlc_mismatch = bb_missing = pol_present = 0

    for sr in sean_rows:
        mid = str(sr.get("market_event_id") or "").strip()
        bb = fetch_binance_strategy_row(mconn, mid) if mid else None
        pol: dict[str, Any] | None = None
        if lconn and mid:
            pol = fetch_policy_evaluation_for_market_event(
                lconn,
                mid,
                lane=RESERVED_STRATEGY_BASELINE,
                strategy_id=RESERVED_STRATEGY_BASELINE,
                signal_mode=SIGNAL_MODE_JUPITER_3,
            )
            if pol:
                pol_present += 1

        line: dict[str, Any] = {
            "market_event_id": mid,
            "sean_close": sr.get("close_px"),
            "blackbox_close": bb.get("close") if bb else None,
            "policy_trade": pol.get("trade") if pol else None,
            "policy_reason": pol.get("reason_code") if pol else None,
        }

        if not bb:
            bb_missing += 1
            line["ohlc_status"] = "blackbox_bar_missing"
        else:
            sc = _f(sr.get("close_px"))
            bc = _f(bb.get("close"))
            if sc is not None and bc is not None and abs(sc - bc) <= OHLC_EPS:
                line["ohlc_status"] = "match"
                ohlc_match += 1
            else:
                line["ohlc_status"] = "mismatch"
                line["close_delta"] = (sc - bc) if (sc is not None and bc is not None) else None
                ohlc_mismatch += 1

        out_rows.append(line)

    mconn.close()
    if lconn:
        lconn.close()

    summary = {
        "sean_rows": len(sean_rows),
        "ohlc_match": ohlc_match,
        "ohlc_mismatch": ohlc_mismatch,
        "blackbox_bar_missing": bb_missing,
        "policy_present": pol_present,
    }
    plain = [
        f"Sean parity rows (latest per bar): {summary['sean_rows']}",
        f"OHLC match (close vs binance_strategy_bars_5m): {summary['ohlc_match']}",
        f"OHLC mismatch: {summary['ohlc_mismatch']}",
        f"Blackbox bar missing: {summary['blackbox_bar_missing']}",
        f"policy_evaluations (sean_jupiter_v3) present: {summary['policy_present']}",
    ]
    return {
        "schema": "jup_v3_parity_compare_v1",
        "ok": True,
        "error": None,
        "summary": summary,
        "rows": out_rows,
        "plain_english": "\n".join(plain),
    }


def main_cli() -> None:
    import argparse

    p = argparse.ArgumentParser(description="JUPv3 Sean SQLite vs Blackbox parity")
    p.add_argument("sean_sqlite", type=Path, help="Path to sean_parity.db")
    p.add_argument("--market-db", type=Path, default=None)
    p.add_argument("--ledger-db", type=Path, default=None)
    p.add_argument("--json", action="store_true", help="Print full JSON")
    args = p.parse_args()
    out = compare_sean_sqlite_to_blackbox(
        sean_sqlite_path=args.sean_sqlite,
        market_db_path=args.market_db,
        ledger_db_path=args.ledger_db,
    )
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(out.get("plain_english") or "")
        if out.get("rows"):
            print("\n--- detail (first 20) ---")
            for r in (out["rows"] or [])[:20]:
                print(r)


if __name__ == "__main__":
    main_cli()
