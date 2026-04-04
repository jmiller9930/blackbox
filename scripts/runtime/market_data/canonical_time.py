"""Single UTC 5m bar clock — bucket math, exclusive close, ISO formatting. Do not duplicate elsewhere."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

FIVE_MINUTES = timedelta(minutes=5)
_BUCKET_SECONDS = 300


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def floor_utc_to_5m_open(dt: datetime) -> datetime:
    """Floor ``dt`` to the start of its containing 5-minute UTC bucket. ``dt`` must be timezone-aware."""
    if dt.tzinfo is None:
        raise ValueError("floor_utc_to_5m_open requires timezone-aware datetime")
    dt = dt.astimezone(timezone.utc)
    epoch = int(dt.timestamp())
    bucket = (epoch // _BUCKET_SECONDS) * _BUCKET_SECONDS
    return datetime.fromtimestamp(bucket, tz=timezone.utc).replace(microsecond=0)


def candle_close_utc_exclusive(candle_open_utc: datetime) -> datetime:
    """Exclusive end of the bucket: ticks with ``t < close`` belong to the bar (``t >= open``)."""
    return candle_open_utc + FIVE_MINUTES


def last_closed_candle_open_utc(now: datetime | None = None) -> datetime:
    """Open UTC time of the most recently *closed* 5m bar (the bar before the current open bucket)."""
    now = now if now is not None else utc_now()
    current_open = floor_utc_to_5m_open(now)
    return current_open - FIVE_MINUTES


def format_candle_open_iso_z(candle_open_utc: datetime) -> str:
    """ISO 8601 Zulu with second precision (used inside market_event_id)."""
    dt = candle_open_utc.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
