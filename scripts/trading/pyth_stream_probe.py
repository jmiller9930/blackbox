#!/usr/bin/env python3
"""
Pyth status artifacts from ``market_ticks`` (SQLite) — no Hermes HTTP.

Writes docs/working/artifacts/pyth_stream_*.json for UI/API readiness.
Used by UIUX.Web docker-compose ``pyth-stream`` service.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_SOL_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
_INTERVAL = float(os.environ.get("PYTH_STREAM_INTERVAL_SEC", "15"))
_TICK_SYMBOL = (os.environ.get("MARKET_TICK_SYMBOL") or "SOL-USD").strip() or "SOL-USD"


def _repo_root() -> Path:
    return Path(os.environ.get("BLACKBOX_REPO_ROOT", "/repo")).resolve()


def _market_db_path() -> Path:
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or "").strip()
    if raw:
        return Path(raw).resolve()
    return _repo_root() / "data" / "sqlite" / "market_data.db"


def _artifacts() -> Path:
    d = _repo_root() / "docs" / "working" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fetch_latest() -> dict[str, Any]:
    """Latest SOL-USD tick from SQLite — same price the recorder uses for Pyth."""
    db = _market_db_path()
    fid = (os.environ.get("PYTH_SOL_USD_FEED_ID") or _DEFAULT_SOL_FEED).strip()
    if not db.is_file():
        return {
            "ok": False,
            "error": f"market_data_db_missing:{db}",
            "price": None,
            "publish_time": None,
            "feed_id": fid,
        }
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            """
            SELECT primary_price, primary_publish_time, inserted_at
            FROM market_ticks
            WHERE symbol = ?
            ORDER BY inserted_at DESC, id DESC
            LIMIT 1
            """,
            (_TICK_SYMBOL,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return {"ok": False, "error": "no_ticks", "price": None, "publish_time": None, "feed_id": fid}
    price, pub, ins_at = row
    if price is None:
        return {
            "ok": False,
            "error": "primary_price_null",
            "price": None,
            "publish_time": int(pub) if pub is not None else None,
            "feed_id": fid,
            "inserted_at": ins_at,
        }
    try:
        pub_i = int(pub) if pub is not None else None
    except (TypeError, ValueError):
        pub_i = None
    return {
        "ok": True,
        "error": None,
        "price": float(price),
        "publish_time": pub_i,
        "feed_id": fid,
        "inserted_at": str(ins_at) if ins_at is not None else None,
    }


def _write_status(art: Path, snap: dict[str, Any], now: datetime) -> None:
    ok = snap.get("ok") is True
    iso = now.replace(microsecond=0).isoformat()
    event_iso = snap.get("inserted_at") or iso
    if ok:
        stream = {
            "status": "healthy",
            "stream_state": "connected",
            "reason_code": "pyth_sqlite_tape_ok",
            "last_event_at": event_iso,
            "updated_at": iso,
            "stale_after_seconds": 120,
            "price": snap.get("price"),
            "publish_time": snap.get("publish_time"),
            "feed_id": snap.get("feed_id"),
        }
    else:
        stream = {
            "status": "degraded",
            "stream_state": "error",
            "reason_code": f"pyth_probe_failed:{snap.get('error') or 'unknown'}",
            "last_event_at": event_iso,
            "updated_at": iso,
            "stale_after_seconds": 120,
        }
    (art / "pyth_stream_status.json").write_text(json.dumps(stream, indent=2) + "\n", encoding="utf-8")

    recent_path = art / "pyth_stream_recent.json"
    prev: dict[str, Any] = {}
    if recent_path.exists():
        try:
            prev = json.loads(recent_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    items = list(prev.get("items") or []) if isinstance(prev.get("items"), list) else []
    if ok and snap.get("price") is not None:
        items.append(
            {
                "price": snap["price"],
                "publish_time": snap.get("publish_time"),
                "observed_at": event_iso,
            }
        )
    items = items[-48:]
    recent_path.write_text(json.dumps({"items": items}, indent=2) + "\n", encoding="utf-8")

    safety = art / "pyth_storage_safety.json"
    if not safety.exists():
        safety.write_text(
            json.dumps({"max_db_bytes": 40 * 1024**3, "target_db_bytes": 36 * 1024**3}, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    art = _artifacts()
    print(
        f"pyth_stream_probe: repo={_repo_root()} db={_market_db_path()} symbol={_TICK_SYMBOL!r} "
        f"artifacts={art} interval={_INTERVAL}s (SQLite tape, no Hermes HTTP)",
        flush=True,
    )
    while True:
        now = datetime.now(timezone.utc)
        snap = _fetch_latest()
        _write_status(art, snap, now)
        print(
            f"{now.isoformat()} ok={snap.get('ok')} price={snap.get('price')!r} err={snap.get('error')!r}",
            flush=True,
        )
        time.sleep(_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
