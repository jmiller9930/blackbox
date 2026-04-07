"""Parse Hermes SSE ``parsed[]`` price objects (SOL/USD and same-shaped feeds)."""
from __future__ import annotations

import math
from typing import Any


def price_from_hermes_parsed_entry(
    entry: dict[str, Any],
    *,
    conf_ratio_max: float = 0.001,
) -> tuple[float | None, int | None]:
    """
    Return (usd_float, publish_time_unix) from one ``parsed`` array element.
    Skips low-confidence updates when conf/price > ``conf_ratio_max`` (same idea as Drift bot).
    """
    price_obj = entry.get("price")
    if not isinstance(price_obj, dict):
        return None, None
    raw = price_obj.get("price")
    conf = price_obj.get("conf")
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
    try:
        conf_f = float(str(conf)) * (10**expo_i)
    except (TypeError, ValueError):
        conf_f = 0.0
    if val > 0 and conf_f / val > conf_ratio_max:
        return None, int(pub) if pub is not None else None
    pub_i = int(pub) if pub is not None else None
    out = float(val)
    if math.isnan(out) or math.isinf(out):
        return None, pub_i
    return out, pub_i
