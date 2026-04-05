"""
Time-aligned chart overlays for the operator dashboard (baseline, Anna strategies, survival tests).

Segments are derived from ledger trade entry/exit times mapped onto the visible bar window — not
single-bar horizontal placeholders as the only representation when times exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    query_trades_for_symbol_timeframe_in_events,
    query_trades_for_symbol_timeframe_overlapping_window,
)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _bars_chronological(history_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """API returns newest-first; chart uses oldest → recent left to right."""
    return list(reversed(history_bars))


def _mid_to_index(bars: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, b in enumerate(bars):
        mid = str(b.get("market_event_id") or "").strip()
        if mid:
            out[mid] = i
    return out


def _bar_index_for_time(ts: datetime | None, bars: list[dict[str, Any]]) -> int | None:
    if ts is None or not bars:
        return None
    for i, b in enumerate(bars):
        co = _parse_iso(str(b.get("candle_open_utc") or ""))
        cc = _parse_iso(str(b.get("candle_close_utc") or ""))
        if co and cc and co <= ts < cc:
            return i
    # nearest bar by candle_open
    best_i = None
    best_d = None
    for i, b in enumerate(bars):
        co = _parse_iso(str(b.get("candle_open_utc") or ""))
        if not co:
            continue
        d = abs((ts - co).total_seconds())
        if best_d is None or d < best_d:
            best_d = d
            best_i = i
    return best_i


def _segment_for_trade(
    row: dict[str, Any],
    mid_index: dict[str, int],
    bars: list[dict[str, Any]],
) -> tuple[int, int, float | None]:
    """Returns (from_bar, to_bar, entry_price) clamped to window."""
    n = len(bars)
    if n == 0:
        return 0, 0, None
    ep = row.get("entry_price")

    mid = str(row.get("market_event_id") or "").strip()
    entry_i = mid_index.get(mid)
    et = _parse_iso(str(row.get("entry_time") or ""))
    xt = _parse_iso(str(row.get("exit_time") or ""))

    if entry_i is None and et is not None:
        entry_i = _bar_index_for_time(et, bars)
    if entry_i is None:
        entry_i = 0

    exit_i: int | None = None
    if xt is not None:
        exit_i = _bar_index_for_time(xt, bars)
    if exit_i is None and str(row.get("exit_time") or "").strip():
        exit_i = entry_i
    if exit_i is None:
        exit_i = n - 1

    a = max(0, min(n - 1, int(entry_i)))
    b = max(0, min(n - 1, int(exit_i)))
    if b < a:
        a, b = b, a
    try:
        pf = float(ep) if ep is not None else None
    except (TypeError, ValueError):
        pf = None
    return a, b, pf


def _dedupe_trades(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        tid = str(r.get("trade_id") or "")
        if tid and tid in seen:
            continue
        if tid:
            seen.add(tid)
        out.append(r)
    return out


def build_chart_overlay(
    *,
    history_bars: list[dict[str, Any]],
    symbol: str | None,
    timeframe: str | None,
    allowed_anna_strategy_ids: list[str] | None,
    survival_tests_active: list[dict[str, Any]],
    db_path: Path,
) -> dict[str, Any]:
    """
    Build overlay metadata for the market chart + test strip.

    If ``allowed_anna_strategy_ids`` is None, every Anna lane segment in the window is included
    (full/debug). Otherwise segments are restricted to that id set. Baseline is always included.
    """
    bars = _bars_chronological(history_bars)
    n = len(bars)
    if n == 0 or not symbol or not timeframe:
        return {
            "schema": "chart_overlay_v1",
            "bar_count": 0,
            "bars_timeline": [],
            "baseline_position_segments": [],
            "strategy_position_segments": [],
            "survival_test_bands": [],
            "render_semantics": _semantics(),
            "data_gaps": ["missing_symbol_timeframe_or_bars"],
        }

    mids = [str(b.get("market_event_id") or "") for b in bars if b.get("market_event_id")]
    mid_index = _mid_to_index(bars)

    first_open = str(bars[0].get("candle_open_utc") or "")
    last_close = str(bars[-1].get("candle_close_utc") or "") or first_open

    in_events = query_trades_for_symbol_timeframe_in_events(
        symbol.strip(),
        timeframe.strip(),
        mids,
        db_path=db_path,
    )
    spanning = query_trades_for_symbol_timeframe_overlapping_window(
        symbol.strip(),
        timeframe.strip(),
        first_open,
        last_close,
        db_path=db_path,
    )
    merged = _dedupe_trades(in_events + spanning)

    allowed_set: set[str] | None = None
    if allowed_anna_strategy_ids is not None:
        allowed_set = {str(s).strip() for s in allowed_anna_strategy_ids if str(s).strip()}

    baseline_segments: list[dict[str, Any]] = []
    strategy_segments: list[dict[str, Any]] = []

    for row in merged:
        lane = str(row.get("lane") or "").strip().lower()
        sid = str(row.get("strategy_id") or "").strip()
        a, b, price = _segment_for_trade(row, mid_index, bars)
        if price is None:
            continue
        seg = {
            "from_bar": a,
            "to_bar": b,
            "entry_price": price,
            "trade_id": str(row.get("trade_id") or ""),
            "strategy_id": sid,
            "lane": lane,
            "mode": str(row.get("mode") or ""),
        }
        if lane == "baseline" or sid == RESERVED_STRATEGY_BASELINE:
            baseline_segments.append(seg)
        elif lane == "anna":
            if allowed_set is None or sid in allowed_set:
                strategy_segments.append(seg)

    bands: list[dict[str, Any]] = []
    for i, t in enumerate(survival_tests_active or []):
        ct = _parse_iso(str(t.get("created_at_utc") or ""))
        bi = _bar_index_for_time(ct, bars) if ct else 0
        bi = max(0, min(n - 1, bi if bi is not None else 0))
        status = str(t.get("status") or "")
        to_b = n - 1
        bands.append(
            {
                "test_id": str(t.get("test_id") or ""),
                "strategy_id": str(t.get("strategy_id") or ""),
                "status": status,
                "from_bar": bi,
                "to_bar": to_b,
                "strip_row": i % 4,
            }
        )

    timeline = [
        {
            "i": i,
            "market_event_id": str(b.get("market_event_id") or ""),
            "candle_open_utc": str(b.get("candle_open_utc") or ""),
        }
        for i, b in enumerate(bars)
    ]

    gaps: list[str] = []
    if not merged:
        gaps.append("no_ledger_trades_in_window")

    return {
        "schema": "chart_overlay_v1",
        "bar_count": n,
        "bars_timeline": timeline,
        "baseline_position_segments": baseline_segments,
        "strategy_position_segments": strategy_segments,
        "survival_test_bands": bands,
        "render_semantics": _semantics(),
        "data_gaps": gaps,
    }


def _semantics() -> dict[str, str]:
    return {
        "price_path": "Primary OHLC is candlesticks (UI); overlay segments merge to stepped lines per lane/strategy.",
        "baseline": "Ledger baseline_position_segments: entry_price held from entry bar through exit (or window end).",
        "strategies": "strategy_position_segments per strategy_id; UI draws one stepped line per strategy (max five).",
        "tests": "Separate strip below price: each band spans bars (ongoing evaluation), not a price line.",
    }
