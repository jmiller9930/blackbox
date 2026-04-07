#!/usr/bin/env python3
"""
Hermes Pyth **SSE** → ``market_ticks`` (full stream, one row per update).

Subscribes to ``/v2/updates/price/stream`` (not ``latest_price_feeds`` polling).
Each SSE ``data:`` JSON with a ``parsed`` price update is inserted into
``BLACKBOX_MARKET_DATA_PATH`` / default ``data/sqlite/market_data.db``.

Environment:
  PYTH_SOL_USD_FEED_ID — 64-hex feed id (default: SOL/USD)
  MARKET_TICK_SYMBOL — logical symbol (default SOL-USD)
  PYTH_SSE_DEDUPE_PUBLISH_TIME — if 1 (default), skip duplicate ``publish_time``
  PYTH_SSE_CONF_RATIO_MAX — max conf/price to accept (default 0.001, match Drift bot)
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


def _dedupe_publish() -> bool:
    return (os.environ.get("PYTH_SSE_DEDUPE_PUBLISH_TIME", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ))


def _sse_url() -> str:
    fid = _feed_id()
    return f"https://hermes.pyth.network/v2/updates/price/stream?ids[]={fid}"


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
    if _dedupe_publish() and pub_i is not None and last_pub[0] == pub_i:
        return False
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
        gate_reason="pyth_sse_stream_ingest",
    )
    return True


def _run_sse_loop() -> None:
    db_path = default_market_data_path()
    root = repo_root()
    conn = connect_market_db(db_path)
    ensure_market_schema(conn, root)
    symbol = _symbol()
    url = _sse_url()
    last_pub: list[int | None] = [None]
    print(
        f"pyth_sse_ingest: db={db_path} symbol={symbol!r} url={url[:64]}… "
        f"dedupe_publish={_dedupe_publish()}",
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
                                            data, conn=conn, symbol=symbol, last_pub=last_pub
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
