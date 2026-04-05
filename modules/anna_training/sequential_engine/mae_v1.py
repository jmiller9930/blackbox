"""
MAE USD v1 — single canonical rule (no alternate runtime paths).

Protocol id is hashed into manifests and protocol bundles.

Rule (deterministic, 5m bars only):
  - Load all ``market_bars_5m`` rows for the trade's ``canonical_symbol`` where
    ``candle_open_utc`` is in the closed UTC window [entry_time, exit_time]
    (inclusive by string comparison after normalizing to ISO-8601 UTC).
  - For each bar, adverse USD relative to ``entry_price`` and ``size`` (positive notional):
      * long:  max(0, (entry_price - low) * size)
      * short: max(0, (high - entry_price) * size)
  - MAE_USD = max over bars; 0 if there are no qualifying bars (empty window).

Excluded / not computable cases return ``None`` and the caller should mark EXCLUDED.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAE_PROTOCOL_ID = "mae_usd_v1_ledger_bars_5m"


def _default_market_db_path() -> Path:
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_DB") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(__file__).resolve().parents[3] / "data" / "sqlite" / "market_data.db"


def _parse_ts_utc(s: str | None) -> datetime | None:
    if not s or not str(s).strip():
        return None
    raw = str(s).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _ts_key(dt: datetime) -> str:
    """Comparable ISO string for SQL range queries (UTC)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


@dataclass(frozen=True)
class MaeV1Inputs:
    """Inputs required for MAE v1 (hashed for audit)."""

    mae_protocol_id: str
    canonical_symbol: str
    side: str
    entry_price: float
    size: float
    entry_time_utc: str
    exit_time_utc: str
    market_db_path: str


def fetch_bars_in_trade_window(
    *,
    canonical_symbol: str,
    entry_time: str | None,
    exit_time: str | None,
    market_db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return 5m bars ordered by candle_open_utc ascending; empty if DB missing or none."""
    p = market_db_path or _default_market_db_path()
    if not p.is_file():
        return []
    t0 = _parse_ts_utc(entry_time)
    t1 = _parse_ts_utc(exit_time)
    if t0 is None or t1 is None:
        return []
    if t1 < t0:
        return []
    sym = (canonical_symbol or "").strip()
    if not sym:
        return []
    k0 = _ts_key(t0)
    k1 = _ts_key(t1)
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars_5m'"
        )
        if cur.fetchone() is None:
            return []
        cur = conn.execute(
            """
            SELECT candle_open_utc, high, low, open, close, market_event_id
            FROM market_bars_5m
            WHERE canonical_symbol = ?
              AND candle_open_utc >= ?
              AND candle_open_utc <= ?
            ORDER BY candle_open_utc ASC
            """,
            (sym, k0, k1),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "candle_open_utc": r[0],
                "high": r[1],
                "low": r[2],
                "open": r[3],
                "close": r[4],
                "market_event_id": r[5],
            }
        )
    return out


def compute_mae_usd_v1(
    *,
    canonical_symbol: str,
    side: str | None,
    entry_price: float | None,
    size: float | None,
    entry_time: str | None,
    exit_time: str | None,
    market_db_path: Path | None = None,
) -> tuple[float | None, str | None]:
    """
    Returns (mae_usd, exclusion_reason).

    exclusion_reason is set when MAE cannot be computed (None mae).
    """
    sd = (side or "").strip().lower()
    if sd not in ("long", "short"):
        return None, "mae_side_invalid"
    if entry_price is None or size is None:
        return None, "mae_price_size_missing"
    try:
        ep = float(entry_price)
        sz = float(size)
    except (TypeError, ValueError):
        return None, "mae_price_size_invalid"
    if sz <= 0 or not (ep == ep):  # nan check
        return None, "mae_price_size_invalid"

    bars = fetch_bars_in_trade_window(
        canonical_symbol=canonical_symbol,
        entry_time=entry_time,
        exit_time=exit_time,
        market_db_path=market_db_path,
    )
    if not bars:
        return None, "mae_no_bars_in_window"

    adverse_max = 0.0
    for b in bars:
        try:
            hi = float(b["high"])
            lo = float(b["low"])
        except (TypeError, ValueError, KeyError):
            continue
        if sd == "long":
            adv = max(0.0, (ep - lo) * sz)
        else:
            adv = max(0.0, (hi - ep) * sz)
        if adv > adverse_max:
            adverse_max = adv

    return float(adverse_max), None
