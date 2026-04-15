"""
Hermes tape + canonical bar advancement health (operator watchdog).

Detects silent loss of tick persistence or stalled ``market_bars_5m`` without relying on
subtle UI cues. Emits structured alerts (throttled) when unhealthy.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SCHEMA = "ingest_health_v1"

# Expected Hermes SSE cadence: many rows per minute when stream is healthy.
_DEFAULT_TICK_MAX_AGE_SEC = 180.0  # 3 minutes
# Closed bucket materialization: 5m close + refresh throttle + Binance + bridge.
# Seconds after the **close** of the expected last-closed bucket (open+5m) before flagging bars.
_DEFAULT_BAR_MAX_LAG_SEC = 180.0  # 3 minutes; raise via INGEST_HEALTH_BAR_MAX_LAG_SEC for looser checks

_last_stderr_log_mono: float = 0.0
_stderr_lock = threading.Lock()
_STDERR_LOG_INTERVAL_SEC = 30.0


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_tick_ts(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0)
    except (TypeError, ValueError):
        return None


def _parse_bar_open_iso(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0)
    except (TypeError, ValueError):
        return None


def _emit_throttled_stderr(payload: dict[str, Any]) -> None:
    global _last_stderr_log_mono
    now_m = time.monotonic()
    with _stderr_lock:
        if now_m - _last_stderr_log_mono < _STDERR_LOG_INTERVAL_SEC:
            return
        _last_stderr_log_mono = now_m
    line = json.dumps(payload, default=str, sort_keys=True)
    print(line, file=sys.stderr, flush=True)


def compute_ingest_health(
    *,
    market_db_path: Path,
    now: datetime | None = None,
    canonical_symbol: str = "SOL-PERP",
) -> dict[str, Any]:
    """
    Compare live DB against expected Hermes tick freshness and last-closed 5m bar.

    Tick source filter: ``primary_source = 'pyth_hermes_sse'`` (same as rollup).
    Bar: ``MAX(candle_open_utc)`` for baseline canonical symbol vs
    :func:`market_data.canonical_time.last_closed_candle_open_utc`.
    """
    import sqlite3

    now = now if now is not None else datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc).replace(microsecond=0)

    tick_max_age = _env_float("INGEST_HEALTH_TICK_MAX_AGE_SEC", _DEFAULT_TICK_MAX_AGE_SEC)
    bar_max_lag = _env_float("INGEST_HEALTH_BAR_MAX_LAG_SEC", _DEFAULT_BAR_MAX_LAG_SEC)

    rt = Path(__file__).resolve().parents[2] / "scripts" / "runtime"
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))
    from market_data.canonical_time import format_candle_open_iso_z, last_closed_candle_open_utc

    expected_last_closed = last_closed_candle_open_utc(now)
    expected_iso = format_candle_open_iso_z(expected_last_closed)

    out: dict[str, Any] = {
        "schema": _SCHEMA,
        "market_db_path": str(market_db_path),
        "checked_at_utc": now.isoformat().replace("+00:00", "Z"),
        "thresholds": {
            "tick_max_age_sec": tick_max_age,
            "bar_max_lag_sec": bar_max_lag,
        },
    }

    if not market_db_path.is_file():
        out.update(
            {
                "healthy": False,
                "state": "critical",
                "operator_alert_code": "TAPE_STALLED",
                "message": "market database file missing — tape cannot be evaluated",
                "ui_trust_tape_data": False,
                "tick": {
                    "max_inserted_at": None,
                    "age_seconds": None,
                    "stalled": True,
                },
                "bars": {
                    "canonical_symbol": canonical_symbol,
                    "max_candle_open_utc": None,
                    "expected_last_closed_open_utc": expected_iso,
                    "lag_seconds": None,
                    "stalled": True,
                },
            }
        )
        _emit_throttled_stderr({"event": "INGEST_HEALTH_ALERT", **{k: out[k] for k in ("state", "operator_alert_code", "message", "checked_at_utc")}})
        return out

    conn = sqlite3.connect(str(market_db_path))
    try:
        row_tick = conn.execute(
            """
            SELECT MAX(inserted_at) FROM market_ticks
            WHERE primary_source = 'pyth_hermes_sse'
            """
        ).fetchone()
        max_ins = row_tick[0] if row_tick else None
        tick_dt = _parse_tick_ts(max_ins if isinstance(max_ins, str) else None)
        tick_age = (now - tick_dt).total_seconds() if tick_dt else None
        tick_stalled = True
        if tick_age is not None:
            tick_stalled = tick_age > tick_max_age

        row_bar = conn.execute(
            """
            SELECT MAX(candle_open_utc) FROM market_bars_5m
            WHERE canonical_symbol = ?
            """,
            (canonical_symbol,),
        ).fetchone()
        max_open_s = row_bar[0] if row_bar else None
        stored_open = _parse_bar_open_iso(max_open_s if isinstance(max_open_s, str) else None)

        lag_sec: float | None = None
        # Expected bucket closes at open+5m; allow ``bar_max_lag`` seconds after that for rollup/bridge.
        expected_bucket_close = expected_last_closed + timedelta(minutes=5)
        secs_after_expected_close = (now - expected_bucket_close).total_seconds()

        if stored_open is None:
            bar_stalled = secs_after_expected_close > bar_max_lag
        elif stored_open < expected_last_closed:
            lag_sec = max(0.0, (expected_last_closed - stored_open).total_seconds())
            bar_stalled = secs_after_expected_close > bar_max_lag
        else:
            bar_stalled = False
    finally:
        conn.close()

    healthy = (not tick_stalled) and (not bar_stalled)

    if tick_stalled and bar_stalled:
        state = "critical"
        code = "TAPE_STALLED"
        msg = "Hermes ticks are stale and canonical 5m bars are not advancing — no trustworthy tape."
    elif tick_stalled:
        state = "ingest_down"
        code = "INGEST_DOWN"
        msg = "Hermes SSE ticks are not being persisted — ingest is down or blocked."
    elif bar_stalled:
        state = "bars_stalled"
        code = "BARS_STALLED"
        msg = "Ticks may flow but market_bars_5m is not advancing for the last closed bucket — rollup/bridge stuck."
    else:
        state = "operational"
        code = "NONE"
        msg = "Hermes tape and canonical bar row are within health thresholds."

    out.update(
        {
            "healthy": healthy,
            "state": state,
            "operator_alert_code": code,
            "message": msg,
            "ui_trust_tape_data": healthy,
            "tick": {
                "max_inserted_at": max_ins if isinstance(max_ins, str) else None,
                "age_seconds": tick_age,
                "stalled": tick_stalled,
            },
            "bars": {
                "canonical_symbol": canonical_symbol,
                "max_candle_open_utc": max_open_s if isinstance(max_open_s, str) else None,
                "expected_last_closed_open_utc": expected_iso,
                "lag_seconds": lag_sec,
                "stalled": bar_stalled,
            },
        }
    )

    if not healthy:
        _emit_throttled_stderr(
            {
                "event": "INGEST_HEALTH_ALERT",
                "state": state,
                "operator_alert_code": code,
                "tick_age_seconds": tick_age,
                "bar_max_open": max_open_s,
                "expected_last_closed_open_utc": expected_iso,
                "checked_at_utc": out["checked_at_utc"],
            }
        )

    return out
