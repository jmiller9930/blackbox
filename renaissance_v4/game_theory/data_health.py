"""
SQLite / bar-feed health for the pattern-game UI (no stdout spam — do not use ``get_connection()`` here).

Spec alignment: primary instrument **SOLUSDT** in ``GAME_SPEC_INDICATOR_PATTERN_V1.md``; replay reads **all** rows
in ``market_bars_5m`` (see ``replay_runner``). We report both **all-bars** (replay) and **SOLUSDT** span for the
12‑month style check.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any

from renaissance_v4.research.replay_runner import MIN_ROWS_REQUIRED
from renaissance_v4.utils.db import DB_PATH

# ~11.5 months minimum calendar span on SOLUSDT to show green for "12 months" (ingest gaps).
TWELVE_MONTH_SPAN_MIN_DAYS = 335

MS_PER_DAY = 86400 * 1000

# Same scale as ``evaluation_window_runtime.slice_rows_for_calendar_months`` (approx. Gregorian month).
_CALENDAR_MONTH_APPROX_DAYS = 30.4375


def max_evaluation_window_calendar_months_from_span_days(span_days: float | None) -> int | None:
    """
    Upper bound for operator ``calendar_months`` given tape length (replay loads **all** rows in
    ``market_bars_5m`` ordered by ``open_time`` — same span as this MIN/MAX).

    Uses ``ceil(span_days / month)`` so a ~365-day tape allows 12 months (not 11 from floor).
    """
    if span_days is None or span_days <= 0:
        return None
    m = int(math.ceil(span_days / _CALENDAR_MONTH_APPROX_DAYS))
    return max(1, min(600, m))


def _span_days(min_ms: int | None, max_ms: int | None) -> float | None:
    if min_ms is None or max_ms is None:
        return None
    return (max_ms - min_ms) / MS_PER_DAY


def get_data_health() -> dict[str, Any]:
    """
    Return JSON-serializable status for ``/api/data-health``.

    Keys are stable for the web header; ``overall_ok`` is the single aggregate for green vs red.
    """
    path = DB_PATH.resolve()
    out: dict[str, Any] = {
        "overall_ok": False,
        "database_path": str(path),
        "database_file_exists": path.is_file(),
        "database_open_ok": False,
        "table_market_bars_ok": False,
        "replay_symbol": "SOLUSDT",
        "all_bars_count": 0,
        "all_bars_span_days": None,
        "solusdt_bar_count": 0,
        "solusdt_span_days": None,
        "replay_min_rows": MIN_ROWS_REQUIRED,
        "replay_rows_ok": False,
        "twelve_month_window_ok": False,
        "replay_tape_span_days_approx": None,
        "max_evaluation_window_calendar_months": None,
        "error": None,
        "summary_line": "",
    }

    if not path.is_file():
        out["summary_line"] = "Database file missing — ingest or copy renaissance_v4.sqlite3"
        return out

    try:
        with sqlite3.connect(str(path)) as conn:
            conn.row_factory = sqlite3.Row
            out["database_open_ok"] = True

            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars_5m'"
            ).fetchone()
            if not row:
                out["summary_line"] = "Table market_bars_5m missing — run schema / ingest"
                return out
            out["table_market_bars_ok"] = True

            all_row = conn.execute(
                "SELECT COUNT(*) AS c, MIN(open_time) AS tmin, MAX(open_time) AS tmax FROM market_bars_5m"
            ).fetchone()
            sol_row = conn.execute(
                """
                SELECT COUNT(*) AS c, MIN(open_time) AS tmin, MAX(open_time) AS tmax
                FROM market_bars_5m WHERE symbol = ?
                """,
                ("SOLUSDT",),
            ).fetchone()
    except (OSError, sqlite3.Error) as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["summary_line"] = out["error"]
        return out

    c_all = int(all_row["c"] or 0)
    c_sol = int(sol_row["c"] or 0)
    out["all_bars_count"] = c_all
    out["solusdt_bar_count"] = c_sol
    out["all_bars_span_days"] = _span_days(all_row["tmin"], all_row["tmax"])
    out["solusdt_span_days"] = _span_days(sol_row["tmin"], sol_row["tmax"])
    span_all = out["all_bars_span_days"]
    out["replay_tape_span_days_approx"] = span_all
    out["max_evaluation_window_calendar_months"] = max_evaluation_window_calendar_months_from_span_days(span_all)

    out["replay_rows_ok"] = c_all >= MIN_ROWS_REQUIRED
    sd = out["solusdt_span_days"]
    out["twelve_month_window_ok"] = (
        sd is not None and sd >= TWELVE_MONTH_SPAN_MIN_DAYS and c_sol > 0
    )

    out["overall_ok"] = bool(
        out["database_open_ok"]
        and out["table_market_bars_ok"]
        and out["replay_rows_ok"]
        and out["twelve_month_window_ok"]
    )

    parts = [
        f"DB OK · {c_all} bars (all symbols)",
        f"SOLUSDT {c_sol} bars",
    ]
    if sd is not None:
        parts.append(f"~{sd:.0f}d span")
    if out["twelve_month_window_ok"]:
        parts.append("≥12mo window")
    else:
        parts.append("12mo window short or missing SOLUSDT")
    if not out["replay_rows_ok"]:
        parts.append(f"need ≥{MIN_ROWS_REQUIRED} rows for replay")
    out["summary_line"] = " · ".join(parts)
    return out
