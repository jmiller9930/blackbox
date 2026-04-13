"""
Binance public REST — 5m kline **quote asset volume** for ``market_bars_5m.volume_base``.

Pyth/Hermes supplies **price** ticks only; exchange volume for Jupiter_3 spike vs average comes **only**
from Binance ``/api/v3/klines`` (field index 7, quote asset volume), keyed to the same UTC bar open as
the canonical bar.

Environment:
  BLACKBOX_BINANCE_KLINE_ENABLED — ``1`` (default) fetch quote volume after each closed-bar rollup;
    set ``0`` to skip (tests / airgap).
  BLACKBOX_BINANCE_KLINE_SYMBOL — Binance spot symbol for SOL baseline (default ``SOLUSDT``).
  BLACKBOX_BINANCE_KLINE_TIMEOUT_SEC — HTTP timeout (default ``12``).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from market_data.canonical_bar import CanonicalBarV1
from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP


def _binance_enabled() -> bool:
    raw = (os.environ.get("BLACKBOX_BINANCE_KLINE_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def binance_spot_symbol_for_canonical(canonical_symbol: str) -> str | None:
    """Map internal canonical id to Binance ``symbol`` for klines (spot USDT pair)."""
    c = (canonical_symbol or "").strip()
    if c == CANONICAL_INSTRUMENT_SOL_PERP:
        sym = (os.environ.get("BLACKBOX_BINANCE_KLINE_SYMBOL") or "SOLUSDT").strip().upper()
        return sym or "SOLUSDT"
    return None


def fetch_binance_quote_volume_5m(
    *,
    binance_symbol: str,
    candle_open_utc: datetime,
    timeout_sec: float | None = None,
) -> float | None:
    """
    Return **quote asset volume** (USDT) for the 5m kline whose open time matches ``candle_open_utc``.

    ``None`` on HTTP/parse errors or if the returned kline open time does not match (no silent wrong bar).
    """
    if not isinstance(candle_open_utc, datetime):
        return None
    dt = candle_open_utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    start_ms = int(dt.timestamp() * 1000)

    if timeout_sec is None:
        try:
            timeout_sec = float((os.environ.get("BLACKBOX_BINANCE_KLINE_TIMEOUT_SEC") or "12").strip())
        except ValueError:
            timeout_sec = 12.0
    timeout_sec = max(3.0, min(60.0, float(timeout_sec)))

    qs = urllib.parse.urlencode(
        {
            "symbol": (binance_symbol or "").strip().upper(),
            "interval": "5m",
            "startTime": start_ms,
            "limit": 1,
        }
    )
    url = f"https://api.binance.com/api/v3/klines?{qs}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "blackbox-canonical-bar/1 (+binance klines volume)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(data, list) or len(data) < 1:
        return None
    row = data[0]
    if not isinstance(row, (list, tuple)) or len(row) < 8:
        return None
    try:
        k_open_ms = int(row[0])
    except (TypeError, ValueError):
        return None
    if k_open_ms != start_ms:
        return None
    try:
        return float(row[7])
    except (TypeError, ValueError):
        return None


def enrich_canonical_bar_volume_from_binance(bar: CanonicalBarV1) -> tuple[CanonicalBarV1, dict[str, Any]]:
    """
    Set ``volume_base`` from Binance 5m kline quote volume; leave OHLC/tick_count from Pyth rollup unchanged.

    Returns ``(bar, meta)`` where ``meta`` describes fetch outcome for logging/API.
    """
    meta: dict[str, Any] = {"schema": "binance_kline_volume_enrich_v1"}
    if not _binance_enabled():
        meta["skipped"] = "disabled"
        return bar, meta

    sym = binance_spot_symbol_for_canonical(bar.canonical_symbol)
    if sym is None:
        meta["skipped"] = "no_binance_symbol_mapping"
        return bar, meta

    qv = fetch_binance_quote_volume_5m(binance_symbol=sym, candle_open_utc=bar.candle_open_utc)
    meta["binance_symbol"] = sym
    if qv is None:
        meta["skipped"] = "fetch_failed_or_bar_mismatch"
        return bar, meta

    meta["quote_volume_usdt"] = qv
    return replace(bar, volume_base=qv), meta
