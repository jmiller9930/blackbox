"""
Binance-authoritative 5m OHLCV for **Jupiter_3 only** — populates ``binance_strategy_bars_5m``.

V2 / ``market_bars_5m`` (Pyth rollup + optional quote-volume enrich) is **not** modified.

Uses ``GET /api/v3/klines`` with ``limit`` up to 1000 (Binance max per call), same host as
``binance_kline_volume``.

Environment:
  BLACKBOX_BINANCE_KLINE_SYMBOL — Binance spot symbol (default ``SOLUSDT``).
  BLACKBOX_BINANCE_STRATEGY_KLINE_LIMIT — default ``1000`` (max 1000).
  BLACKBOX_BINANCE_KLINE_TIMEOUT_SEC — HTTP timeout (default ``20``).

**Scheduling:** This module does not run on a timer by itself. Production must use
``binance_strategy_bars_sync_loop.py`` (see ``UIUX.Web/docker-compose.yml`` service
``binance-strategy-bars-sync``) or an equivalent cron/systemd job; otherwise the table
stalls after the last manual run.
Default loop interval is **30s** (floor **15s**); each successful run writes SQLite **and**
a hot JSON snapshot (``binance_strategy_latest_*.json`` beside the DB) for fast dashboard reads.

**Catch-up:** After the primary fetch, :func:`_catch_up_binance_strategy_to_clock` runs so a missed
closed bucket (e.g. long loop interval) is repaired immediately instead of waiting for the next cycle.

Environment (additional):
  BLACKBOX_BINANCE_STRATEGY_BACKFILL_MAX_ROUNDS — max catch-up fetch rounds per run (default ``12``).
``BLACKBOX_JUPV3_MAX_ACCEPTABLE_CLOSED_BUCKET_LAG`` is consumed by the dashboard bundle contract
(``modules/anna_training/jup_v3_freshness_contract.py``), not this script.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_data.binance_kline_volume import _ssl_context, binance_spot_symbol_for_canonical
from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP, TICK_SYMBOL_SOL_DEFAULT, TIMEFRAME_5M
from market_data.canonical_time import (
    candle_close_utc_exclusive,
    format_candle_open_iso_z,
    last_closed_candle_open_utc,
    parse_iso_zulu_to_utc,
)
from market_data.market_event_id import make_market_event_id
from market_data.store import connect_market_db, ensure_market_schema, upsert_binance_strategy_bar_5m


def _strategy_kline_limit() -> int:
    try:
        n = int((os.environ.get("BLACKBOX_BINANCE_STRATEGY_KLINE_LIMIT") or "1000").strip())
    except ValueError:
        n = 1000
    return max(1, min(1000, n))


def _backfill_max_rounds() -> int:
    try:
        n = int((os.environ.get("BLACKBOX_BINANCE_STRATEGY_BACKFILL_MAX_ROUNDS") or "12").strip())
    except ValueError:
        n = 12
    return max(1, min(48, n))


def _timeout_sec() -> float:
    try:
        t = float((os.environ.get("BLACKBOX_BINANCE_KLINE_TIMEOUT_SEC") or "20").strip())
    except ValueError:
        t = 20.0
    return max(5.0, min(60.0, t))


def fetch_binance_klines_5m_chunk(
    *,
    binance_symbol: str,
    limit: int,
    end_ms: int | None = None,
) -> list[list[Any]] | None:
    """Return raw kline rows from Binance (newest last in list per API convention)."""
    lim = max(1, min(1000, int(limit)))
    qs: dict[str, Any] = {
        "symbol": (binance_symbol or "").strip().upper(),
        "interval": "5m",
        "limit": lim,
    }
    if end_ms is not None:
        qs["endTime"] = int(end_ms)
    url = f"https://api.binance.com/api/v3/klines?{urllib.parse.urlencode(qs)}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "blackbox-binance-strategy-bars/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_timeout_sec(), context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"binance_strategy_bars_sync: fetch failed {exc!r}", file=sys.stderr, flush=True)
        return None
    if not isinstance(data, list):
        return None
    return data


def _parse_kline_row(
    cand: list[Any] | tuple[Any, ...],
) -> tuple[datetime, float, float, float, float, float, float] | None:
    try:
        open_ms = int(cand[0])
        o = float(cand[1])
        h = float(cand[2])
        l = float(cand[3])
        c = float(cand[4])
        base_vol = float(cand[5])
        qv = float(cand[7])
    except (TypeError, ValueError, IndexError):
        return None
    dt = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc).replace(microsecond=0)
    return dt, o, h, l, c, base_vol, qv


def _upsert_closed_klines_from_raw(
    conn: Any,
    raw: list[list[Any]],
    *,
    canonical_symbol: str,
    tick_symbol: str,
    tf: str,
    now_ms: int,
) -> dict[str, Any]:
    """Upsert closed 5m klines only; returns counts and max open written."""
    n_ok = 0
    n_skip = 0
    max_open_written: str | None = None
    for cand in raw:
        if not isinstance(cand, (list, tuple)) or len(cand) < 8:
            n_skip += 1
            continue
        try:
            close_ms = int(cand[6])
            if close_ms > now_ms:
                n_skip += 1
                continue
        except (TypeError, ValueError):
            pass
        parsed = _parse_kline_row(cand)
        if parsed is None:
            n_skip += 1
            continue
        candle_open_utc, o, h, l, c, base_vol, qv = parsed
        close_boundary = candle_close_utc_exclusive(candle_open_utc)
        meid = make_market_event_id(
            canonical_symbol=canonical_symbol,
            candle_open_utc=candle_open_utc,
            timeframe=tf,
        )
        co_iso = format_candle_open_iso_z(candle_open_utc)
        upsert_binance_strategy_bar_5m(
            conn,
            canonical_symbol=canonical_symbol,
            tick_symbol=tick_symbol,
            timeframe=tf,
            candle_open_utc=co_iso,
            candle_close_utc=format_candle_open_iso_z(close_boundary),
            market_event_id=meid,
            open_px=o,
            high_px=h,
            low_px=l,
            close_px=c,
            volume_base_asset=base_vol,
            quote_volume_usdt=qv,
        )
        n_ok += 1
        max_open_written = co_iso
    return {
        "rows_upserted": n_ok,
        "rows_skipped": n_skip,
        "max_candle_open_utc_written": max_open_written,
    }


def _db_max_binance_strategy_open(conn: Any, canonical_symbol: str) -> str | None:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='binance_strategy_bars_5m'"
    )
    if cur.fetchone() is None:
        return None
    row = conn.execute(
        """
        SELECT MAX(candle_open_utc) FROM binance_strategy_bars_5m
        WHERE timeframe = '5m' AND canonical_symbol = ?
        """,
        (canonical_symbol,),
    ).fetchone()
    if not row or row[0] is None:
        return None
    return str(row[0]).strip()


def _catch_up_binance_strategy_to_clock(
    conn: Any,
    *,
    binance_symbol: str,
    canonical_symbol: str,
    tick_symbol: str,
    tf: str,
) -> dict[str, Any]:
    """
    If DB newest closed bar is older than ``last_closed_candle_open_utc()``, fetch again with a
    fresh ``endTime`` and upsert until caught up or max rounds. Does **not** replace periodic sync;
    it repairs missed buckets between loop iterations.
    """
    exp = last_closed_candle_open_utc()
    exp_iso = format_candle_open_iso_z(exp)
    rounds = 0
    total_ok = 0
    max_r = _backfill_max_rounds()
    last_db: str | None = None
    while rounds < max_r:
        db_raw = _db_max_binance_strategy_open(conn, canonical_symbol)
        last_db = db_raw
        if not db_raw:
            break
        try:
            db_dt = parse_iso_zulu_to_utc(db_raw)
        except ValueError:
            break
        if db_dt >= exp:
            break
        now_ms = int(time.time() * 1000)
        lim = min(500, _strategy_kline_limit())
        raw = fetch_binance_klines_5m_chunk(binance_symbol=binance_symbol, limit=lim, end_ms=now_ms)
        if raw is None:
            break
        u = _upsert_closed_klines_from_raw(
            conn,
            raw,
            canonical_symbol=canonical_symbol,
            tick_symbol=tick_symbol,
            tf=tf,
            now_ms=now_ms,
        )
        total_ok += int(u.get("rows_upserted") or 0)
        if int(u.get("rows_upserted") or 0) == 0:
            break
        rounds += 1
    return {
        "catch_up_rounds": rounds,
        "catch_up_rows_upserted": total_ok,
        "canonical_expected_last_closed_candle_open_utc": exp_iso,
        "db_max_candle_open_utc_before": last_db,
        "db_max_candle_open_utc_after": _db_max_binance_strategy_open(conn, canonical_symbol),
    }


def sync_binance_strategy_bars_into_db(
    *,
    db_path: Path,
    canonical_symbol: str = CANONICAL_INSTRUMENT_SOL_PERP,
) -> dict[str, Any]:
    """
    Fetch recent closed 5m klines and upsert ``binance_strategy_bars_5m``.

    Returns a status dict (counts, errors).
    """
    sym = binance_spot_symbol_for_canonical(canonical_symbol)
    if not sym:
        return {"ok": False, "reason": "no_binance_symbol_mapping", "canonical_symbol": canonical_symbol}

    lim = _strategy_kline_limit()
    raw = fetch_binance_klines_5m_chunk(binance_symbol=sym, limit=lim)
    if raw is None:
        return {"ok": False, "reason": "fetch_failed", "binance_symbol": sym}

    tick_symbol = TICK_SYMBOL_SOL_DEFAULT
    tf = TIMEFRAME_5M
    conn = connect_market_db(db_path)
    n_ok = 0
    n_skip = 0
    max_open_written: str | None = None
    catch_up: dict[str, Any] = {}
    wall_utc = ""
    try:
        ensure_market_schema(conn)
        now_ms = int(time.time() * 1000)
        u0 = _upsert_closed_klines_from_raw(
            conn,
            raw,
            canonical_symbol=canonical_symbol,
            tick_symbol=tick_symbol,
            tf=tf,
            now_ms=now_ms,
        )
        n_ok = int(u0.get("rows_upserted") or 0)
        n_skip = int(u0.get("rows_skipped") or 0)
        max_open_written = u0.get("max_candle_open_utc_written")
        catch_up = _catch_up_binance_strategy_to_clock(
            conn,
            binance_symbol=sym,
            canonical_symbol=canonical_symbol,
            tick_symbol=tick_symbol,
            tf=tf,
        )
        if catch_up.get("catch_up_rows_upserted"):
            n_ok += int(catch_up.get("catch_up_rows_upserted") or 0)
            max_open_written = catch_up.get("db_max_candle_open_utc_after") or max_open_written
        wall_utc = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        from market_data.bar_lookup import write_binance_strategy_latest_snapshot

        write_binance_strategy_latest_snapshot(
            conn,
            db_path,
            canonical_symbol,
            sync_wall_utc_iso=wall_utc,
        )
    finally:
        conn.close()

    return {
        "ok": True,
        "binance_symbol": sym,
        "klines_fetched": len(raw),
        "rows_upserted": n_ok,
        "rows_skipped": n_skip,
        "limit_requested": lim,
        "wall_clock_utc": wall_utc,
        "max_candle_open_utc_written": max_open_written,
        "catch_up": catch_up,
    }


def main() -> None:
    from _paths import default_market_data_path

    db = default_market_data_path()
    out = sync_binance_strategy_bars_into_db(db_path=db)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
