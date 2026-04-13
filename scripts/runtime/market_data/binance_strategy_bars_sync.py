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
from market_data.canonical_time import candle_close_utc_exclusive, format_candle_open_iso_z
from market_data.market_event_id import make_market_event_id
from market_data.store import connect_market_db, ensure_market_schema, upsert_binance_strategy_bar_5m


def _strategy_kline_limit() -> int:
    try:
        n = int((os.environ.get("BLACKBOX_BINANCE_STRATEGY_KLINE_LIMIT") or "1000").strip())
    except ValueError:
        n = 1000
    return max(1, min(1000, n))


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
    n_ok = 0
    n_skip = 0
    conn = connect_market_db(db_path)
    try:
        ensure_market_schema(conn)
        now_ms = int(time.time() * 1000)
        for cand in raw:
            if not isinstance(cand, (list, tuple)) or len(cand) < 8:
                n_skip += 1
                continue
            # Binance appends the **current** open candle as the last row; close time (index 6) is
            # still in the future until the bucket closes. Skip — V3 evaluates **closed** bars only.
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
            upsert_binance_strategy_bar_5m(
                conn,
                canonical_symbol=canonical_symbol,
                tick_symbol=tick_symbol,
                timeframe=tf,
                candle_open_utc=format_candle_open_iso_z(candle_open_utc),
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
    finally:
        conn.close()

    return {
        "ok": True,
        "binance_symbol": sym,
        "klines_fetched": len(raw),
        "rows_upserted": n_ok,
        "rows_skipped": n_skip,
        "limit_requested": lim,
    }


def main() -> None:
    from _paths import default_market_data_path

    db = default_market_data_path()
    out = sync_binance_strategy_bars_into_db(db_path=db)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
