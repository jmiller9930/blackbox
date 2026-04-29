"""
GT055 — Triple-barrier outcome labels (TP / SL / time exit).

Maps Referee ``exit_reason`` strings to {-1, 0, +1} without changing execution engines.
Used for learning-record enrichment and walk-forward proof analysis.
"""

from __future__ import annotations

import os
from typing import Any


def triple_barrier_labels_enabled_v1() -> bool:
    return (os.environ.get("GT055_TRIPLE_BARRIER_LABELS_V1") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def triple_barrier_label_v1(exit_reason: str | None) -> int:
    """
    +1 = TP / target hit first, -1 = SL / stop hit first, 0 = time-like exit or unknown/neutral.
    """
    s = str(exit_reason or "").strip().lower()
    if not s:
        return 0
    if s in ("target", "take_profit", "tp", "take profit"):
        return 1
    if s in ("stop", "stop_loss", "sl", "stop loss"):
        return -1
    if any(
        x in s
        for x in (
            "time",
            "timeout",
            "flatten",
            "session",
            "replay_end",
            "end_of",
            "expire",
        )
    ):
        return 0
    if "profit" in s or "target" in s or s.endswith("_tp"):
        return 1
    if "stop" in s or s.endswith("_sl"):
        return -1
    return 0


def bars_held_v1(
    entry_time_ms: int | None,
    exit_time_ms: int | None,
    *,
    candle_timeframe_minutes: int,
) -> int | None:
    """Closed bars spanned by hold window (at least 1 when times valid)."""
    try:
        et = int(entry_time_ms) if entry_time_ms is not None else None
        ex = int(exit_time_ms) if exit_time_ms is not None else None
    except (TypeError, ValueError):
        return None
    if et is None or ex is None or ex < et:
        return None
    tf_ms = max(1, int(candle_timeframe_minutes)) * 60 * 1000
    return max(1, int((ex - et + tf_ms - 1) // tf_ms))


def enrich_referee_subset_triple_barrier_v1(
    referee_subset: dict[str, Any],
    *,
    referee_truth_v1: dict[str, Any],
    candle_timeframe_minutes: int,
) -> dict[str, Any]:
    """Return a copy of ``referee_subset`` with triple-barrier fields when inputs allow."""
    out = dict(referee_subset)
    er = referee_truth_v1.get("exit_reason")
    out["triple_barrier_label_v1"] = int(triple_barrier_label_v1(str(er) if er is not None else None))
    et = referee_truth_v1.get("entry_time_ms")
    xt = referee_truth_v1.get("exit_time_ms")
    out["entry_time_ms"] = et
    out["exit_time_ms"] = xt
    ep = referee_truth_v1.get("entry_price")
    xp = referee_truth_v1.get("exit_price")
    if ep is not None:
        out["entry_price"] = float(ep)
    if xp is not None:
        out["exit_price"] = float(xp)
    bh = bars_held_v1(et, xt, candle_timeframe_minutes=int(candle_timeframe_minutes))
    if bh is not None:
        out["bars_held_v1"] = int(bh)
    sl = referee_truth_v1.get("stop_loss")
    tp = referee_truth_v1.get("take_profit")
    if sl is not None:
        try:
            out["stop_loss"] = float(sl)
        except (TypeError, ValueError):
            pass
    if tp is not None:
        try:
            out["take_profit"] = float(tp)
        except (TypeError, ValueError):
            pass
    return out


__all__ = [
    "bars_held_v1",
    "enrich_referee_subset_triple_barrier_v1",
    "triple_barrier_label_v1",
    "triple_barrier_labels_enabled_v1",
]
