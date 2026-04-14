#!/usr/bin/env python3
"""
Sandbox: Hermes SSE → in-memory 5m buckets → **V** (tick count) + OHLC.

**No SQLite, no API, no dashboard** — same parse path as production tape
(``tape_price_and_publish_from_entry``): every valid Hermes ``parsed[]`` counts.

Use to compare **V** against Sean’s in-process counter or Black Box DB for the **same**
``candle_open_utc`` (run during that window or inspect printed buckets).

From repo root::

  PYTHONPATH=scripts/runtime python3 scripts/trading/hermes_sse_sandbox_v.py --seconds 120

While running, prints ``V=`` for the latest 5m bucket every 10s (see ``run(..., progress_sec=...)`` to change).

Environment (optional): ``PYTH_SOL_USD_FEED_ID``, ``PYTH_HERMES_BASE_URL`` — same as ``pyth_sse_ingest``.
"""
from __future__ import annotations

import argparse
import http.client
import json
import ssl
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts" / "runtime"))

from market_data.canonical_time import floor_utc_to_5m_open, format_candle_open_iso_z  # noqa: E402
from market_data.hermes_sse_price import (  # noqa: E402
    tape_price_and_publish_from_entry,
)
from market_data.public_data_urls import hermes_price_stream_url  # noqa: E402

USER_AGENT = "blackbox-hermes-sse-sandbox-v/1"
_DEFAULT_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx


def _sse_url() -> str:
    import os

    fid = (os.environ.get("PYTH_SOL_USD_FEED_ID") or _DEFAULT_FEED).strip()
    return hermes_price_stream_url(fid)


def _bucket_key_for_publish_unix(pub_i: int) -> str:
    dt = datetime.fromtimestamp(pub_i, tz=timezone.utc)
    floored = floor_utc_to_5m_open(dt)
    return format_candle_open_iso_z(floored)


def _ohlc_from_prices(prices: list[float]) -> tuple[float, float, float, float] | None:
    if not prices:
        return None
    return prices[0], max(prices), min(prices), prices[-1]


def run(*, duration_sec: float, progress_sec: float = 10.0) -> int:
    url = _sse_url()
    # bucket_key -> ordered prices
    buckets: dict[str, list[float]] = defaultdict(list)
    raw_lines = 0
    parsed_ok = 0
    skipped_no_pub = 0
    start = time.monotonic()
    deadline = start + duration_sec
    last_progress_print = start

    def maybe_print_progress(*, force: bool = False) -> None:
        nonlocal last_progress_print
        if progress_sec <= 0:
            return
        now = time.monotonic()
        if not force and (now - last_progress_print) < progress_sec:
            return
        last_progress_print = now
        elapsed = now - start
        rem = max(0.0, deadline - now)
        if not buckets:
            print(
                f"sandbox_v: elapsed={elapsed:.0f}s remaining={rem:.0f}s  V=0  (no ticks yet)  "
                f"sse_lines={raw_lines}",
                flush=True,
            )
            return
        k_max = max(buckets.keys())
        v_now = len(buckets[k_max])
        print(
            f"sandbox_v: elapsed={elapsed:.0f}s remaining={rem:.0f}s  bar={k_max}  V={v_now}  "
            f"total_inserts={parsed_ok}  sse_lines={raw_lines}",
            flush=True,
        )

    def handle_data(data: str) -> None:
        nonlocal raw_lines, parsed_ok, skipped_no_pub
        raw_lines += 1
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return
        parsed = payload.get("parsed")
        if not isinstance(parsed, list) or not parsed:
            return
        entry = parsed[0]
        if not isinstance(entry, dict):
            return
        px, pub_i = tape_price_and_publish_from_entry(entry)
        if px is None:
            return
        if pub_i is None:
            skipped_no_pub += 1
            return
        parsed_ok += 1
        key = _bucket_key_for_publish_unix(pub_i)
        buckets[key].append(px)
        maybe_print_progress()

    ctx = _ssl_context()  # noqa: E701
    parsed_url = urlparse(url)
    host = parsed_url.netloc or "hermes.pyth.network"
    path_qs = parsed_url.path or "/"
    if parsed_url.query:
        path_qs = f"{path_qs}?{parsed_url.query}"

    print(f"sandbox_v: duration={duration_sec}s url={url[:72]}…", flush=True)

    hc = http.client.HTTPSConnection(host, context=ctx, timeout=60)
    hc.request(
        "GET",
        path_qs,
        headers={"Accept": "text/event-stream", "User-Agent": USER_AGENT, "Connection": "keep-alive"},
    )
    resp = hc.getresponse()
    if resp.status != 200:
        print(f"sandbox_v: HTTP {resp.status}", file=sys.stderr)
        hc.close()
        return 1
    try:
        if hc.sock:
            hc.sock.settimeout(5.0)
    except OSError:
        pass

    buf = b""
    try:
        while time.monotonic() < deadline:
            chunk = resp.read(8192)
            maybe_print_progress(force=False)
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
                            handle_data(data)
    finally:
        hc.close()
        maybe_print_progress(force=True)

    print("", flush=True)
    print(f"sandbox_v: sse_data_lines={raw_lines} tape_inserts={parsed_ok} skipped_no_publish_time={skipped_no_pub}", flush=True)
    if not buckets:
        print("sandbox_v: no buckets (no ticks with publish_time)", flush=True)
        return 0

    keys = sorted(buckets.keys())
    print("", flush=True)
    print("5m buckets (oracle publish_time, full tape, no DB):", flush=True)
    for k in keys:
        prices = buckets[k]
        ohlc = _ohlc_from_prices(prices)
        v = len(prices)
        if ohlc is None:
            continue
        o, h, l_, c = ohlc
        print(
            f"  Timestamp={k}  V={v}  O={o:.8f}  H={h:.8f}  L={l_:.8f}  C={c:.8f}",
            flush=True,
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Hermes SSE in-memory V/OHLC sandbox (no DB).")
    ap.add_argument(
        "--seconds",
        type=float,
        default=90.0,
        help="How long to read the stream (default 90).",
    )
    args = ap.parse_args()
    return run(duration_sec=max(5.0, float(args.seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
