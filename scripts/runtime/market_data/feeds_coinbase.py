"""Coinbase Exchange public REST — comparator feed (Phase 5.1)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = "blackbox-market-data/5.1 (+read-only)"
SOURCE = "coinbase_exchange_public_rest"


@dataclass(frozen=True)
class NormalizedQuote:
    source: str
    symbol: str
    price: float | None
    observed_at: str
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


def fetch_coinbase_ticker(product_id: str, *, timeout: float = 20.0) -> NormalizedQuote:
    """GET Coinbase Exchange product ticker (read-only)."""
    pid = product_id.strip()
    url = f"https://api.exchange.coinbase.com/products/{pid}/ticker"
    notes: list[str] = []
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        notes.append(f"coinbase_ticker_failed:{type(e).__name__}:{e}")
        return NormalizedQuote(
            source=SOURCE,
            symbol=pid,
            price=None,
            observed_at=None,
            notes=notes,
            raw={},
        )

    last = _f(raw.get("price"))
    notes.append("Coinbase Exchange GET /products/{id}/ticker (read-only).")
    if last is None:
        notes.append("coinbase_missing_price")
        return NormalizedQuote(
            source=SOURCE,
            symbol=pid,
            price=None,
            observed_at=None,
            notes=notes,
            raw=dict(raw),
        )
    return NormalizedQuote(
        source=SOURCE,
        symbol=pid,
        price=last,
        observed_at=observed_at,
        notes=notes,
        raw=dict(raw),
    )
