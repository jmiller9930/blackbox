"""Canonical 5m OHLC bar from ticks — bars are identity; ticks are input."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from market_data.canonical_instrument import TIMEFRAME_5M
from market_data.canonical_time import candle_close_utc_exclusive, format_candle_open_iso_z
from market_data.market_event_id import make_market_event_id


@dataclass(frozen=True)
class CanonicalBarV1:
    """Authoritative bar object for storage, API, and market_event_id."""

    canonical_symbol: str
    tick_symbol: str
    timeframe: str
    candle_open_utc: datetime
    candle_close_utc: datetime  # exclusive boundary for membership
    market_event_id: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    tick_count: int
    volume_base: float | None
    price_source: str
    bar_schema_version: str = "canonical_bar_v1"

    def to_row_dict(self) -> dict[str, Any]:
        return {
            "canonical_symbol": self.canonical_symbol,
            "tick_symbol": self.tick_symbol,
            "timeframe": self.timeframe,
            "candle_open_utc": format_candle_open_iso_z(self.candle_open_utc),
            "candle_close_utc": format_candle_open_iso_z(self.candle_close_utc),
            "market_event_id": self.market_event_id,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tick_count": self.tick_count,
            "volume_base": self.volume_base,
            "price_source": self.price_source,
            "bar_schema_version": self.bar_schema_version,
        }


def build_canonical_bar_from_ticks(
    *,
    ticks: list[dict[str, Any]],
    tick_symbol: str,
    canonical_symbol: str,
    candle_open_utc: datetime,
    timeframe: str = TIMEFRAME_5M,
    price_source: str = "pyth_primary",
) -> CanonicalBarV1 | None:
    """
    Aggregate ``ticks`` (``market_ticks`` row dicts, chronological) into one OHLC bar.
    Returns ``None`` if no ticks or no valid primary_price.
    """
    close_boundary = candle_close_utc_exclusive(candle_open_utc)
    prices: list[float] = []
    for t in ticks:
        p = t.get("primary_price")
        if p is None:
            continue
        try:
            prices.append(float(p))
        except (TypeError, ValueError):
            continue
    if not prices:
        return None
    o = prices[0]
    c = prices[-1]
    hi = max(prices)
    lo = min(prices)
    meid = make_market_event_id(
        canonical_symbol=canonical_symbol,
        timeframe=timeframe,
        candle_open_utc=candle_open_utc,
    )
    return CanonicalBarV1(
        canonical_symbol=canonical_symbol,
        tick_symbol=tick_symbol,
        timeframe=timeframe,
        candle_open_utc=candle_open_utc,
        candle_close_utc=close_boundary,
        market_event_id=meid,
        open=o,
        high=hi,
        low=lo,
        close=c,
        tick_count=len(ticks),
        volume_base=None,
        price_source=price_source,
    )
