"""
Anna data grounding — read-only live market lookups (v1).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

_BINANCE_BOOK_TICKER = "https://api.binance.com/api/v3/ticker/bookTicker"
_TIMEOUT_SECONDS = 4.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s.startswith("$"):
        s = s[1:]
    if s.endswith("USDT"):
        s = s[:-4]
    return s


def _book_ticker_symbol(symbol: str) -> str:
    return f"{_normalize_symbol(symbol)}USDT"


def _fetch_book_ticker(symbol: str) -> dict[str, Any]:
    as_of = _now_iso()
    base = _normalize_symbol(symbol)
    if not base:
        return {
            "ok": False,
            "symbol": "",
            "source": "binance",
            "as_of": as_of,
            "note": "missing symbol",
        }
    pair = _book_ticker_symbol(base)
    qs = urllib.parse.urlencode({"symbol": pair})
    url = f"{_BINANCE_BOOK_TICKER}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "blackbox-anna/4.6.3.5A"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "symbol": base,
            "source": "binance",
            "as_of": as_of,
            "note": f"http_error:{exc.code}",
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "symbol": base,
            "source": "binance",
            "as_of": as_of,
            "note": f"network_error:{exc.reason}",
        }
    except Exception as exc:  # pragma: no cover - defensive guard
        return {
            "ok": False,
            "symbol": base,
            "source": "binance",
            "as_of": as_of,
            "note": f"unexpected_error:{exc}",
        }

    try:
        bid = float(payload["bidPrice"])
        ask = float(payload["askPrice"])
    except Exception:
        return {
            "ok": False,
            "symbol": base,
            "source": "binance",
            "as_of": as_of,
            "note": "invalid_response_shape",
        }
    if bid <= 0 or ask <= 0 or ask < bid:
        return {
            "ok": False,
            "symbol": base,
            "source": "binance",
            "as_of": as_of,
            "note": "invalid_bid_ask_values",
        }
    spread = ask - bid
    mid = (bid + ask) / 2.0
    return {
        "ok": True,
        "symbol": base,
        "price": mid,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "source": "binance",
        "as_of": as_of,
        "note": "",
    }


def get_price(symbol: str) -> dict[str, Any]:
    """Return midpoint quote from top-of-book as live price proxy."""
    return _fetch_book_ticker(symbol)


def get_spread(symbol: str) -> dict[str, Any]:
    """Return top-of-book bid/ask spread."""
    return _fetch_book_ticker(symbol)
