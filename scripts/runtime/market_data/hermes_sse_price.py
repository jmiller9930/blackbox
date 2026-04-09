"""Parse Hermes SSE ``parsed[]`` price objects — integer ``price`` + ``expo`` only (no rounding policy)."""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any


def hermes_price_identity_from_entry(entry: dict[str, Any]) -> tuple[int, int] | None:
    """
    Exact oracle identity: ``(price_raw_int, expo)`` as Hermes sends them.
    Two ticks differ iff this tuple differs — no float tolerance.
    """
    price_obj = entry.get("price")
    if not isinstance(price_obj, dict):
        return None
    raw = price_obj.get("price")
    expo = price_obj.get("expo")
    try:
        expo_i = int(expo) if expo is not None else 0
    except (TypeError, ValueError):
        expo_i = 0
    try:
        raw_i = int(str(raw))
    except (TypeError, ValueError):
        return None
    return (raw_i, expo_i)


def human_price_float_from_identity(raw_i: int, expo_i: int) -> float:
    """Human USD/SOL price for SQLite / OHLC — ``Decimal`` scale, ``float`` only for storage math."""
    d = Decimal(raw_i) * (Decimal(10) ** expo_i)
    return float(d)


def publish_time_unix_from_entry(entry: dict[str, Any]) -> int | None:
    """Oracle ``publish_time`` seconds from one ``parsed`` element, if present."""
    price_obj = entry.get("price")
    if not isinstance(price_obj, dict):
        return None
    pub = price_obj.get("publish_time")
    try:
        return int(pub) if pub is not None else None
    except (TypeError, ValueError):
        return None


def tape_price_and_publish_from_entry(entry: dict[str, Any]) -> tuple[float | None, int | None]:
    """
    Hermes ``parsed[]`` element → ``(primary_price, publish_time_unix)`` for tape insert.

    **No** confidence filter — if Hermes sent a valid ``(price, expo) identity``, it counts.
    Use when the product requires every broadcast update to be represented in the tape.
    """
    ident = hermes_price_identity_from_entry(entry)
    if ident is None:
        return None, None
    raw_i, expo_i = ident
    val = human_price_float_from_identity(raw_i, expo_i)
    pub_i = publish_time_unix_from_entry(entry)
    if math.isnan(val) or math.isinf(val):
        return None, pub_i
    return val, pub_i


def price_from_hermes_parsed_entry(
    entry: dict[str, Any],
    *,
    conf_ratio_max: float = 0.001,
) -> tuple[float | None, int | None]:
    """
    Return (usd_float, publish_time_unix) from one ``parsed`` array element.
    Skips low-confidence updates when conf/price > ``conf_ratio_max`` (same idea as Drift bot).
    """
    ident = hermes_price_identity_from_entry(entry)
    if ident is None:
        return None, None
    raw_i, expo_i = ident
    price_obj = entry.get("price")
    if not isinstance(price_obj, dict):
        return None, None
    conf = price_obj.get("conf")
    pub = price_obj.get("publish_time")
    val = human_price_float_from_identity(raw_i, expo_i)
    try:
        conf_raw = int(str(conf)) if conf is not None else 0
    except (TypeError, ValueError):
        conf_raw = 0
    conf_f = float(Decimal(conf_raw) * (Decimal(10) ** expo_i))
    if val > 0 and conf_f / val > conf_ratio_max:
        return None, int(pub) if pub is not None else None
    pub_i = int(pub) if pub is not None else None
    if math.isnan(val) or math.isinf(val):
        return None, pub_i
    return val, pub_i
