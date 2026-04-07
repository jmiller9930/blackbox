#!/usr/bin/env python3
"""
Hermes Pyth **SSE** → ``market_ticks`` (oracle tape for 5m OHLC / ``tick_count``).

Subscribes to ``/v2/updates/price/stream`` (not ``latest_price_feeds`` polling).
Inserts into ``BLACKBOX_MARKET_DATA_PATH`` / default ``data/sqlite/market_data.db``.

**Tick rule (product default):** one row **per Pyth price change** — any time the resolved USD
price differs from the last **stored** tick (``PYTH_SSE_TICK_POLICY=price_change``). That fills
each 5m bucket with one tick per distinct price move Hermes delivers (subject to confidence filter).

Environment:
  PYTH_SOL_USD_FEED_ID — 64-hex feed id (default: SOL/USD)
  MARKET_TICK_SYMBOL — logical symbol (default SOL-USD)
  PYTH_SSE_TICK_POLICY — ``price_change`` (default) | ``every_message`` | ``dedupe_publish``
  PYTH_SSE_DEDUPE_PUBLISH_TIME — only for ``dedupe_publish``: skip duplicate ``publish_time`` (default 1)
  PYTH_SSE_CONF_RATIO_MAX — max conf/price to accept (default 0.001, match Drift bot)
  PYTH_SSE_BAR_REFRESH_SEC — throttle for ``refresh_last_closed_bar_from_ticks`` (default 15)
"""
from __future__ import annotations

import http.client
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# scripts/runtime on path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts" / "runtime"))

from _paths import default_market_data_path, repo_root  # noqa: E402
from market_data.hermes_sse_price import price_from_hermes_parsed_entry  # noqa: E402
from market_data.store import connect_market_db, ensure_market_schema, insert_tick  # noqa: E402

USER_AGENT = "blackbox-pyth-sse-ingest/1 (+stream)"
_DEFAULT_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"

_last_bar_refresh_monotonic: float = 0.0


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx


def _feed_id() -> str:
    return (os.environ.get("PYTH_SOL_USD_FEED_ID") or _DEFAULT_FEED).strip()


def _symbol() -> str:
    return (os.environ.get("MARKET_TICK_SYMBOL") or "SOL-USD").strip() or "SOL-USD"


def _conf_ratio_max() -> float:
    raw = (os.environ.get("PYTH_SSE_CONF_RATIO_MAX") or "0.001").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.001


def _bar_refresh_sec() -> float:
    raw = (os.environ.get("PYTH_SSE_BAR_REFRESH_SEC") or "15").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 15.0


def _dedupe_publish() -> bool:
    return (os.environ.get("PYTH_SSE_DEDUPE_PUBLISH_TIME", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ))


def _tick_policy() -> str:
    """Default ``price_change`` = one DB row each time oracle price moves."""
    v = (os.environ.get("PYTH_SSE_TICK_POLICY") or "price_change").strip().lower()
    if v in ("price_change", "every_message", "dedupe_publish"):
        return v
    return "price_change"


def _same_price_for_policy(prev: float | None, px: float) -> bool:
    """True if we should skip insert (price unchanged within tolerance)."""
    if prev is None:
        return False
    tol = max(1e-10, 1e-12 * max(1.0, abs(px)))
    return abs(prev - px) <= tol


def _sse_url() -> str:
    fid = _feed_id()
    return f"https://hermes.pyth.network/v2/updates/price/stream?ids[]={fid}"


def _maybe_refresh_canonical_bar(conn: Any, symbol: str) -> None:
    """Keep ``market_bars_5m`` aligned with the SSE tape (throttled)."""
    global _last_bar_refresh_monotonic  # noqa: PLW0603
    now = time.monotonic()
    if now - _last_bar_refresh_monotonic < _bar_refresh_sec():
        return
    _last_bar_refresh_monotonic = now
    try:
        from market_data.canonical_bar_refresh import refresh_last_closed_bar_from_ticks

        refresh_last_closed_bar_from_ticks(conn, symbol)
    except Exception as e:  # noqa: BLE001
        print(f"pyth_sse_ingest: bar_refresh {e!r}", flush=True)


def _observed_iso_from_publish(pub_i: int | None) -> str:
    if pub_i is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return (
        datetime.fromtimestamp(pub_i, tz=timezone.utc).replace(microsecond=0).isoformat()
    )


def _handle_data_line(
    data: str,
    *,
    conn: Any,
    symbol: str,
    last_pub: list[int | None],
    last_stored_price: list[float | None],
) -> bool:
    """Parse one SSE data payload; insert tick. Returns True if inserted."""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return False
    parsed = payload.get("parsed")
    if not isinstance(parsed, list) or not parsed:
        return False
    entry = parsed[0]
    if not isinstance(entry, dict):
        return False
    px, pub_i = price_from_hermes_parsed_entry(entry, conf_ratio_max=_conf_ratio_max())
    if px is None:
        return False

    policy = _tick_policy()
    if policy == "dedupe_publish":
        if _dedupe_publish() and pub_i is not None and last_pub[0] == pub_i:
            return False
        if pub_i is not None:
            last_pub[0] = pub_i
    elif policy == "price_change":
        if _same_price_for_policy(last_stored_price[0], px):
            return False
        last_stored_price[0] = px
        if pub_i is not None:
            last_pub[0] = pub_i
    else:
        # every_message: one row per successful SSE parse (max density)
        last_stored_price[0] = px
        if pub_i is not None:
            last_pub[0] = pub_i

    inserted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    obs = _observed_iso_from_publish(pub_i)
    insert_tick(
        conn,
        symbol=symbol,
        inserted_at=inserted_at,
        primary_source="pyth_hermes_sse",
        primary_price=px,
        primary_observed_at=obs,
        primary_publish_time=pub_i,
        primary_raw=entry,
        comparator_source="none",
        comparator_price=None,
        comparator_observed_at=None,
        comparator_raw=None,
        gate_state="ok",
        gate_reason=f"pyth_sse_{policy}",
    )
    _maybe_refresh_canonical_bar(conn, symbol)
    return True


def _run_sse_loop() -> None:
    db_path = default_market_data_path()
    root = repo_root()
    conn = connect_market_db(db_path)
    ensure_market_schema(conn, root)
    symbol = _symbol()
    url = _sse_url()
    last_pub: list[int | None] = [None]
    last_stored_price: list[float | None] = [None]
    if _tick_policy() == "price_change":
        try:
            row = conn.execute(
                """
                SELECT primary_price FROM market_ticks
                WHERE symbol = ? AND primary_source = ?
                ORDER BY inserted_at DESC, id DESC LIMIT 1
                """,
                (symbol, "pyth_hermes_sse"),
            ).fetchone()
            if row and row[0] is not None:
                last_stored_price[0] = float(row[0])
        except Exception as e:  # noqa: BLE001
            print(f"pyth_sse_ingest: warm_start_price_warn {e!r}", flush=True)
    pol = _tick_policy()
    print(
        f"pyth_sse_ingest: db={db_path} symbol={symbol!r} tick_policy={pol!r} url={url[:64]}… "
        f"dedupe_publish_legacy={_dedupe_publish()}",
        flush=True,
    )
    ctx = _ssl_context()
    backoff = 2.0
    parsed_url = urlparse(url)
    host = parsed_url.netloc or "hermes.pyth.network"
    path_qs = parsed_url.path or "/"
    if parsed_url.query:
        path_qs = f"{path_qs}?{parsed_url.query}"
    while True:
        try:
            hc = http.client.HTTPSConnection(host, context=ctx, timeout=60)
            hc.request(
                "GET",
                path_qs,
                headers={"Accept": "text/event-stream", "User-Agent": USER_AGENT, "Connection": "keep-alive"},
            )
            resp = hc.getresponse()
            try:
                if hc.sock:
                    hc.sock.settimeout(None)
            except OSError:
                pass
            print(f"pyth_sse_ingest: connected HTTP {resp.status}", flush=True)
            backoff = 2.0
            buf = b""
            try:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n\n" in buf:
                        block, buf = buf.split(b"\n\n", 1)
                        text = block.decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            line = line.strip()
                            if line.startswith("data:"):
                                data = line[5:].strip()
                                if data and data != "[DONE]":
                                    try:
                                        _handle_data_line(
                                            data,
                                            conn=conn,
                                            symbol=symbol,
                                            last_pub=last_pub,
                                            last_stored_price=last_stored_price,
                                        )
                                    except Exception as e:  # noqa: BLE001
                                        print(f"pyth_sse_ingest: row_error {e!r}", flush=True)
            finally:
                hc.close()
        except (OSError, TimeoutError, http.client.HTTPException) as e:
            print(f"pyth_sse_ingest: connection_error {type(e).__name__}:{e} retry in {backoff}s", flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 1.5, 120.0)
        except KeyboardInterrupt:
            break
    conn.close()


if __name__ == "__main__":
    _run_sse_loop()
