"""Pyth primary leg from ``market_ticks`` (SQLite) — no Hermes HTTP."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Any

SOURCE = "pyth_hermes"

# Crypto.SOL/USD — Pyth feed id (metadata; rows may store in raw JSON).
_DEFAULT_SOL_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"


@dataclass(frozen=True)
class NormalizedQuote:
    source: str
    symbol: str
    price: float | None
    observed_at: str | None
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


def load_pyth_quote_from_db(
    conn: sqlite3.Connection,
    *,
    logical_symbol: str = "SOL-USD",
) -> NormalizedQuote:
    """Primary oracle quote from the latest ``market_ticks`` row — no network I/O."""
    from market_data.store import latest_row_primary_leg

    r = latest_row_primary_leg(conn, logical_symbol)
    if r is None:
        return NormalizedQuote(
            source=SOURCE,
            symbol=logical_symbol,
            price=None,
            observed_at=None,
            publish_time=None,
            notes=["pyth_db_empty_no_prior_tick"],
            raw={},
        )
    raw: dict[str, Any] = {}
    raw_txt = r.get("primary_raw_json")
    if raw_txt:
        try:
            if isinstance(raw_txt, str):
                parsed = json.loads(raw_txt)
                raw = parsed if isinstance(parsed, dict) else {"value": parsed}
            elif isinstance(raw_txt, dict):
                raw = raw_txt
        except json.JSONDecodeError:
            raw = {"primary_raw_json_parse_error": True}
    notes = ["pyth_from_market_data_db"]
    pub = r.get("primary_publish_time")
    try:
        pub_i = int(pub) if pub is not None else None
    except (TypeError, ValueError):
        pub_i = None
    obs = r.get("primary_observed_at")
    obs_s = str(obs).strip() if obs is not None else None
    return NormalizedQuote(
        source=str(r.get("primary_source") or SOURCE),
        symbol=logical_symbol,
        price=_f(r.get("primary_price")),
        observed_at=obs_s if obs_s else None,
        publish_time=pub_i,
        notes=notes,
        raw=raw,
    )
