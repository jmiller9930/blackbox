"""
Anna **visible window** — only a short slice of OHLCV is injected into prompts.

The replay engine may use a year or more of bars; the subject does **not** get bar-by-bar access
to that full tape. This module loads the **last** ``N`` minutes worth of bars (by timeframe) so
Anna’s “live chart” perception is intentionally narrow. Retrospective + batch scorecard blocks
(see ``agent_context_bundle``) are the supplied **memory** of prior experiments, not a second
tape viewer.
"""

from __future__ import annotations

import math
import os
import sqlite3
from typing import Any

# Table used by pattern-game replay for SOLUSDT (5m bars).
_DEFAULT_BAR_MINUTES = 5


def _minutes_per_bar_for_table(table: str) -> int:
    t = table.strip().lower()
    if "5m" in t or "_5m" in t:
        return 5
    if "1m" in t or "_1m" in t:
        return 1
    return _DEFAULT_BAR_MINUTES


_ALLOWED_BAR_TABLES = frozenset({"market_bars_5m"})


def fetch_last_bars_for_window(
    *,
    db_path: Any,
    symbol: str,
    table: str,
    window_minutes: float,
    max_rows: int = 500,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Return newest-first rows (dicts) and optional error string.
    """
    p = db_path
    if not p.is_file():
        return [], f"database file missing: {p}"
    tbl = table if table in _ALLOWED_BAR_TABLES else "market_bars_5m"
    per = _minutes_per_bar_for_table(tbl)
    n_bars = max(1, min(max_rows, int(math.ceil(float(window_minutes) / float(per)))))
    try:
        with sqlite3.connect(str(p)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                f"""
                SELECT open_time, symbol, open, high, low, close, volume
                FROM {tbl}
                WHERE symbol = ?
                ORDER BY open_time DESC
                LIMIT ?
                """,
                (symbol, n_bars),
            )
            rows = [dict(r) for r in cur.fetchall()]
    except (OSError, sqlite3.Error) as e:
        return [], f"{type(e).__name__}: {e}"
    return rows, None


def format_visible_window_for_prompt(
    *,
    db_path: Any | None = None,
    window_minutes: float | None = None,
    symbol: str | None = None,
    table: str | None = None,
    max_chars: int = 6000,
) -> str:
    """
    Markdown block for Anna: contract + tiny OHLCV table (oldest→newest for reading).
    """
    from renaissance_v4.utils.db import DB_PATH

    p = db_path or DB_PATH
    sym = (symbol or os.environ.get("ANNA_VISIBLE_WINDOW_SYMBOL", "SOLUSDT")).strip()
    raw_tbl = (table or os.environ.get("ANNA_VISIBLE_WINDOW_TABLE", "market_bars_5m")).strip()
    tbl = raw_tbl if raw_tbl in _ALLOWED_BAR_TABLES else "market_bars_5m"
    try:
        wm = float(window_minutes if window_minutes is not None else os.environ.get("ANNA_VISIBLE_WINDOW_MINUTES", "5"))
    except (TypeError, ValueError):
        wm = 5.0

    rows, err = fetch_last_bars_for_window(
        db_path=p, symbol=sym, table=tbl, window_minutes=wm, max_rows=500
    )
    per = _minutes_per_bar_for_table(tbl)
    approx_minutes_shown = min(wm, len(rows) * per) if rows else 0.0

    contract = (
        "### Visibility contract (read this first)\n\n"
        "- You do **not** receive the full historical tape (months/years of bars). "
        f"The OHLCV table below is at most **~{approx_minutes_shown:.0f} minutes** of market data "
        f"(**last {len(rows)}** `{per}m` bar(s) for `{sym}`), not the entire dataset the Referee may replay.\n"
        "- **Retrospective** and **batch scorecard** sections (when present) are **memory** of prior operator notes "
        "and batch runs — use them to avoid repeating the same experiment; they are **not** a full chart.\n"
        "- **Referee facts** in the task (when present) are **aggregates** from a full replay; they are not a bar feed. "
        "Do not pretend you saw every bar of the replay; reason about the visible window + memory + facts together.\n\n"
    )

    if err:
        body = f"_Visible window unavailable: {err}_\n"
        out = contract + body
        return out if len(out) <= max_chars else out[: max_chars - 20] + "\n… [truncated]\n"

    if not rows:
        body = "_No rows returned for this symbol/table (ingest or check DB)._\n"
        out = contract + body
        return out if len(out) <= max_chars else out[: max_chars - 20] + "\n… [truncated]\n"

    chronological = list(reversed(rows))
    lines = [
        "| open_time (ms) | open | high | low | close | volume |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in chronological:
        lines.append(
            "| {ot} | {o} | {h} | {l} | {c} | {v} |".format(
                ot=r.get("open_time"),
                o=r.get("open"),
                h=r.get("high"),
                l=r.get("low"),
                c=r.get("close"),
                v=r.get("volume"),
            )
        )
    body = "\n".join(lines) + "\n"
    out = contract + body
    if len(out) > max_chars:
        out = contract + body[: max_chars - len(contract) - 40] + "\n… [truncated]\n"
    return out
