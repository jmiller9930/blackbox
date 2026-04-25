"""
Operator **trade window** (candle rollup timeframe) — UI modes, scenario merge, replay rollup.

Tape is ingested as ``market_bars_5m``. When the operator selects a coarser timeframe (15m / 1h / 4h),
replay rolls up consecutive 5m bars into synthetic OHLCV rows **before** the manifest-driven loop.
"""

from __future__ import annotations

from typing import Any

_BASE_BAR_MINUTES = 5

# GT_DIRECTIVE_026TF — one run = one replay bar width; must match operator UI and Student packet rollup.
CANONICAL_CANDLE_TIMEFRAME_MINUTES_V1: frozenset[int] = frozenset((5, 15, 60, 240))


def is_allowed_candle_timeframe_minutes_v1(n: int) -> bool:
    try:
        return int(n) in CANONICAL_CANDLE_TIMEFRAME_MINUTES_V1
    except (TypeError, ValueError):
        return False


def effective_replay_timeframe_from_worker_replay_row_v1(row: Any) -> int:
    """
    Return replay bar width in **minutes** from a parallel worker result row
    (``replay_timeframe_minutes`` from ``run_manifest_replay`` when present, else
    ``replay_data_audit.candle_timeframe_rollup_v1``), or **5** when no rollup was applied.
    """
    if not isinstance(row, dict) or not row.get("ok"):
        return _BASE_BAR_MINUTES
    rtf = row.get("replay_timeframe_minutes")
    if rtf is not None:
        try:
            n = int(rtf)
            if is_allowed_candle_timeframe_minutes_v1(n):
                return n
        except (TypeError, ValueError):
            pass
    rda = row.get("replay_data_audit")
    if not isinstance(rda, dict):
        return _BASE_BAR_MINUTES
    cur = rda.get("candle_timeframe_rollup_v1")
    if not isinstance(cur, dict):
        return _BASE_BAR_MINUTES
    try:
        t = int(cur.get("target_bar_minutes_requested") or 0)
    except (TypeError, ValueError):
        return _BASE_BAR_MINUTES
    if t > _BASE_BAR_MINUTES and cur.get("rollup_applied") is True:
        return t
    return _BASE_BAR_MINUTES


def normalize_candle_timeframe_minutes_v1(
    raw: Any,
    *,
    default: int = _BASE_BAR_MINUTES,
) -> int:
    """
    Coerce a candidate minutes value to 5/15/60/240 or return ``default`` when missing/invalid.
    (Does not apply recipe-specific floors — see ``extract_candle_timeframe_minutes_for_replay``.)
    """
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return int(default)
    if is_allowed_candle_timeframe_minutes_v1(n):
        return n
    return int(default)


def resolve_ui_trade_window(mode: str) -> dict[str, Any]:
    """
    Map UI values ``5m`` | ``15m`` | ``1h`` | ``4h`` to integer minutes per rolled candle.

    Base data remains 5m; coarser values trigger OHLCV rollup in ``run_manifest_replay``.
    """
    m = (mode or "5m").strip().lower()
    presets: dict[str, tuple[int, str]] = {
        "5m": (5, "5m"),
        "15m": (15, "15m"),
        "1h": (60, "1 hour"),
        "4h": (240, "4 hours"),
    }
    if m not in presets:
        raise ValueError("trade_window_mode must be one of: 5m, 15m, 1h, 4h")
    minutes, label = presets[m]
    return {
        "trade_window_mode": m,
        "candle_timeframe_minutes": minutes,
        "candle_timeframe_label": label,
    }


def annotate_scenarios_with_candle_timeframe(
    scenarios: list[dict[str, Any]],
    *,
    resolved: dict[str, Any],
) -> None:
    """Merge candle timeframe fields into each scenario's ``evaluation_window`` audit block."""
    minutes = int(resolved["candle_timeframe_minutes"])
    mode = str(resolved["trade_window_mode"])
    label = str(resolved.get("candle_timeframe_label") or mode)
    for s in scenarios:
        ew_prev = s.get("evaluation_window") if isinstance(s.get("evaluation_window"), dict) else {}
        base = dict(ew_prev)
        base.update(
            {
                "candle_timeframe_minutes": minutes,
                "candle_timeframe_ui_mode": mode,
                "candle_timeframe_label": label,
                "candle_timeframe_base_source_table": "market_bars_5m",
                "candle_timeframe_referee_note": (
                    f"Replay OHLCV is rolled up from 5m base bars into ~{label} candles "
                    f"({minutes} minutes per bar; consecutive {minutes // _BASE_BAR_MINUTES}×5m rows per candle) "
                    "before strategy evaluation."
                ),
            }
        )
        s["evaluation_window"] = base


def extract_candle_timeframe_minutes_for_replay(scenario: dict[str, Any]) -> int:
    """Minutes per replay bar; defaults to 5 when absent or invalid."""
    ew = scenario.get("evaluation_window")
    if not isinstance(ew, dict):
        return _BASE_BAR_MINUTES
    cm = ew.get("candle_timeframe_minutes")
    try:
        n = int(cm)
    except (TypeError, ValueError):
        return _BASE_BAR_MINUTES
    if n < _BASE_BAR_MINUTES:
        return _BASE_BAR_MINUTES
    if n % _BASE_BAR_MINUTES != 0:
        return _BASE_BAR_MINUTES
    return n


def _row_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {str(k): row[k] for k in row.keys()}
    return {
        "symbol": row[0],
        "open_time": row[1],
        "open": row[2],
        "high": row[3],
        "low": row[4],
        "close": row[5],
        "volume": row[6],
    }


def _agg_ohlcv_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    first = group[0]
    last = group[-1]
    hi = max(float(r["high"]) for r in group)
    lo = min(float(r["low"]) for r in group)
    vol = sum(float(r["volume"]) for r in group)
    return {
        "symbol": first["symbol"],
        "open_time": first["open_time"],
        "open": float(first["open"]),
        "high": hi,
        "low": lo,
        "close": float(last["close"]),
        "volume": vol,
    }


def rollup_5m_rows_to_candle_timeframe(
    rows: list[Any],
    *,
    target_minutes: int,
    base_minutes: int = _BASE_BAR_MINUTES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Roll consecutive base bars into coarser OHLCV rows by **chunking** ``target/base`` bars each.

    Rows are sorted by ``open_time`` ascending, then grouped in fixed-size chunks (e.g. three 5m
    rows per 15m candle). The last chunk may be shorter (partial final candle).

    ``open_time`` on each output row is the **first** constituent bar's ``open_time`` (same units as
    the database). ``high``/``low``/``close``/``volume`` follow standard candle rollup rules.
    """
    from renaissance_v4.game_theory.evaluation_window_runtime import parse_bar_open_time_unix

    n_in = len(rows)
    audit: dict[str, Any] = {
        "schema": "pattern_game_candle_timeframe_rollup_v1",
        "base_bar_minutes": int(base_minutes),
        "target_bar_minutes_requested": int(target_minutes),
        "bars_per_output_candle": None,
        "dataset_bars_before_rollup": n_in,
        "rollup_applied": False,
        "dataset_bars_after_rollup": n_in,
        "note": None,
    }
    if n_in == 0:
        audit["note"] = "No rows — rollup skipped."
        return [], audit

    if target_minutes <= base_minutes:
        out = [_row_dict(r) for r in rows]
        audit["note"] = "Target <= base — passthrough (no rollup)."
        return out, audit

    if target_minutes % base_minutes != 0:
        raise ValueError(
            f"target_minutes ({target_minutes}) must be a multiple of base_minutes ({base_minutes})"
        )

    ratio = int(target_minutes // base_minutes)
    audit["bars_per_output_candle"] = ratio
    dict_rows = sorted((_row_dict(r) for r in rows), key=lambda d: int(d.get("open_time") or 0))
    out: list[dict[str, Any]] = []
    for i in range(0, len(dict_rows), ratio):
        chunk = dict_rows[i : i + ratio]
        if chunk:
            out.append(_agg_ohlcv_group(chunk))

    audit["rollup_applied"] = len(out) < n_in
    audit["dataset_bars_after_rollup"] = len(out)
    audit["bar_window_open_time_start"] = parse_bar_open_time_unix(out[0]) if out else None
    audit["bar_window_open_time_end"] = parse_bar_open_time_unix(out[-1]) if out else None
    return out, audit
