"""Single constructor for market_event_id — Training Architect contract."""

from __future__ import annotations

import re
from datetime import datetime

from market_data.canonical_instrument import TIMEFRAME_5M
from market_data.canonical_time import format_candle_open_iso_z

_MARKET_EVENT_ID_RE = re.compile(
    r"^(?P<sym>.+)_(?P<tf>5m)_(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$"
)


def make_market_event_id(
    *,
    canonical_symbol: str,
    candle_open_utc: datetime,
    timeframe: str = TIMEFRAME_5M,
) -> str:
    """
    ``market_event_id = {canonical_symbol}_{timeframe}_{candle_open_timestamp}``

    ``candle_open_timestamp`` is ISO 8601 Z from :func:`format_candle_open_iso_z` only.
    """
    sym = (canonical_symbol or "").strip()
    tf = (timeframe or "").strip()
    if not sym or not tf:
        raise ValueError("canonical_symbol and timeframe are required")
    ts = format_candle_open_iso_z(candle_open_utc)
    return f"{sym}_{tf}_{ts}"


def parse_market_event_id(s: str) -> tuple[str, str, str] | None:
    """Parse a string produced by :func:`make_market_event_id`; else ``None``."""
    m = _MARKET_EVENT_ID_RE.match((s or "").strip())
    if not m:
        return None
    return m.group("sym"), m.group("tf"), m.group("ts")


def is_valid_market_event_id_format(s: str) -> bool:
    return parse_market_event_id(s) is not None
