"""Aggregate paper trades to a daily P&L series (UTC date)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def daily_pnl_series_from_trades(trades: list[dict[str, Any]]) -> pd.Series | None:
    """
    Sum ``pnl_usd`` by calendar day (UTC). Index: date; values: USD P&L.
    Returns None if no parseable rows.
    """
    rows: list[tuple[pd.Timestamp, float]] = []
    for t in trades:
        if not isinstance(t, dict):
            continue
        raw = str(t.get("ts_utc") or "").strip()
        if not raw:
            continue
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            d = dt.astimezone(timezone.utc).date()
            pnl = float(t.get("pnl_usd") or 0)
            rows.append((pd.Timestamp(d), pnl))
        except (ValueError, TypeError):
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["day", "pnl"])
    s = df.groupby("day")["pnl"].sum().sort_index()
    return s


def daily_returns_from_levels(daily_pnl: pd.Series) -> pd.Series:
    """Simple daily returns: r_t = pnl_t / (cumulative_{t-1} + 1) with floor to avoid div0."""
    eq = daily_pnl.cumsum()
    prev = eq.shift(1).fillna(0.0)
    base = prev.abs() + 1.0
    return daily_pnl / base
