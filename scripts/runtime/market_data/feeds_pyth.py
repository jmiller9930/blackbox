"""Pyth Hermes HTTP — primary-oriented feed (Phase 5.1)."""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "blackbox-market-data/5.1 (+read-only)"
SOURCE = "pyth_hermes"

# Crypto.SOL/USD — Pyth Hermes feed id (64 hex chars; override via PYTH_SOL_USD_FEED_ID).
_DEFAULT_SOL_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"


@dataclass(frozen=True)
class NormalizedQuote:
    source: str
    symbol: str
    price: float | None
    observed_at: str
    publish_time: int | None
    notes: list[str]
    raw: dict[str, Any]


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _price_from_pyth_payload(entry: dict[str, Any]) -> tuple[float | None, int | None]:
    price_obj = entry.get("price")
    if not isinstance(price_obj, dict):
        return None, None
    raw = price_obj.get("price")
    expo = price_obj.get("expo")
    pub = price_obj.get("publish_time")
    try:
        expo_i = int(expo) if expo is not None else 0
    except (TypeError, ValueError):
        expo_i = 0
    try:
        raw_i = int(str(raw))
    except (TypeError, ValueError):
        return None, int(pub) if pub is not None else None
    val = raw_i * (10**expo_i)
    pub_i = int(pub) if pub is not None else None
    return val, pub_i


def fetch_pyth_latest(
    *,
    feed_id: str | None = None,
    logical_symbol: str = "SOL-USD",
    timeout: float = 20.0,
) -> NormalizedQuote:
    """GET Hermes latest_price_feeds for one feed id."""
    fid = (feed_id or os.environ.get("PYTH_SOL_USD_FEED_ID") or _DEFAULT_SOL_FEED).strip()
    qs = urlencode([("ids[]", fid)])
    url = f"https://hermes.pyth.network/api/latest_price_feeds?{qs}"
    notes: list[str] = []
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        notes.append(f"pyth_hermes_failed:{type(e).__name__}:{e}")
        return NormalizedQuote(
            source=SOURCE,
            symbol=logical_symbol,
            price=None,
            observed_at=None,
            publish_time=None,
            notes=notes,
            raw={},
        )

    if not isinstance(body, list) or not body:
        notes.append("pyth_hermes_empty_response")
        return NormalizedQuote(
            source=SOURCE,
            symbol=logical_symbol,
            price=None,
            observed_at=None,
            publish_time=None,
            notes=notes,
            raw={"response": body},
        )

    entry = body[0]
    if not isinstance(entry, dict):
        notes.append("pyth_hermes_bad_entry_shape")
        return NormalizedQuote(
            source=SOURCE,
            symbol=logical_symbol,
            price=None,
            observed_at=None,
            publish_time=None,
            notes=notes,
            raw={},
        )

    px, pub_i = _price_from_pyth_payload(entry)
    if px is None:
        notes.append("pyth_hermes_unparseable_price")
        return NormalizedQuote(
            source=SOURCE,
            symbol=logical_symbol,
            price=None,
            observed_at=None,
            publish_time=pub_i,
            notes=notes,
            raw=entry,
        )
    if pub_i is not None:
        observed_at = datetime.fromtimestamp(pub_i, tz=timezone.utc).replace(microsecond=0).isoformat()
    else:
        observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    notes.append("Hermes GET /api/latest_price_feeds (read-only).")
    return NormalizedQuote(
        source=SOURCE,
        symbol=logical_symbol,
        price=px,
        observed_at=observed_at,
        publish_time=pub_i,
        notes=notes,
        raw=entry,
    )
