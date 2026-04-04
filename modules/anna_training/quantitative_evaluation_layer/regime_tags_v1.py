"""
Minimal regime vocabulary (v1): volatility bucket, trend bucket, optional stress flag.

Intentionally small — not an academic taxonomy.
"""

from __future__ import annotations

from typing import Any

VOL_LOW = "vol_low"
VOL_MID = "vol_mid"
VOL_HIGH = "vol_high"
TREND_UP = "trend_up"
TREND_DOWN = "trend_down"
TREND_FLAT = "trend_flat"


def regime_tags_v1_from_bar(
    bar: dict[str, Any] | None,
    *,
    vol_low_below: float = 0.003,
    vol_mid_below: float = 0.012,
    flat_abs_pct: float = 0.0005,
    gate_state: str | None = None,
) -> dict[str, Any]:
    """
    Derive tags from canonical OHLC bar dict (open, high, low, close).

    stress: True when vol is high bucket OR gate_state in (blocked, degraded).
    """
    out: dict[str, Any] = {
        "schema": "regime_tags_v1",
        "vol_bucket": None,
        "trend_bucket": None,
        "stress": False,
    }
    if not bar:
        return out
    o = _f(bar.get("open"))
    h = _f(bar.get("high"))
    l_ = _f(bar.get("low"))
    c = _f(bar.get("close"))
    if c is None or c <= 0 or h is None or l_ is None:
        return out
    range_pct = (h - l_) / c
    if range_pct < vol_low_below:
        vb = VOL_LOW
    elif range_pct < vol_mid_below:
        vb = VOL_MID
    else:
        vb = VOL_HIGH
    out["vol_bucket"] = vb
    stress = vb == VOL_HIGH
    if o is not None and o > 0:
        chg = (c - o) / o
        if abs(chg) <= flat_abs_pct:
            tb = TREND_FLAT
        elif chg > 0:
            tb = TREND_UP
        else:
            tb = TREND_DOWN
        out["trend_bucket"] = tb
    gs = (gate_state or "").strip().lower()
    if gs in ("blocked", "degraded"):
        stress = True
    out["stress"] = bool(stress)
    return out


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        v = float(x)
        return v if v == v else None  # noqa: PLR0124
    except (TypeError, ValueError):
        return None
