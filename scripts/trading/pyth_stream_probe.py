#!/usr/bin/env python3
"""
Hermes Pyth poller for UI/API artifacts. Writes docs/working/artifacts/pyth_stream_*.json.
Used by UIUX.Web docker-compose `pyth-stream` service (read-only HTTPS to hermes.pyth.network).
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "blackbox-pyth-stream-probe/1 (+read-only)"
_DEFAULT_SOL_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
_INTERVAL = float(os.environ.get("PYTH_STREAM_INTERVAL_SEC", "15"))


def _repo_root() -> Path:
    return Path(os.environ.get("BLACKBOX_REPO_ROOT", "/repo")).resolve()


def _artifacts() -> Path:
    d = _repo_root() / "docs" / "working" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx


def _fetch_latest() -> dict[str, Any]:
    fid = (os.environ.get("PYTH_SOL_USD_FEED_ID") or _DEFAULT_SOL_FEED).strip()
    qs = urlencode([("ids[]", fid)])
    url = f"https://hermes.pyth.network/api/latest_price_feeds?{qs}"
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    ctx = _ssl_context()
    try:
        with urlopen(req, timeout=25.0, context=ctx) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}:{e}",
            "price": None,
            "publish_time": None,
        }
    if not isinstance(body, list) or not body:
        return {"ok": False, "error": "empty_response", "price": None, "publish_time": None}
    entry = body[0]
    if not isinstance(entry, dict):
        return {"ok": False, "error": "bad_entry", "price": None, "publish_time": None}
    price_obj = entry.get("price")
    if not isinstance(price_obj, dict):
        return {"ok": False, "error": "no_price", "price": None, "publish_time": None}
    raw = price_obj.get("price")
    expo = price_obj.get("expo")
    pub = price_obj.get("publish_time")
    try:
        expo_i = int(expo) if expo is not None else 0
        raw_i = int(str(raw))
        val = raw_i * (10**expo_i)
    except (TypeError, ValueError):
        return {"ok": False, "error": "unparseable_price", "price": None, "publish_time": None}
    pub_i = int(pub) if pub is not None else None
    return {"ok": True, "error": None, "price": val, "publish_time": pub_i, "feed_id": fid}


def _write_status(art: Path, snap: dict[str, Any], now: datetime) -> None:
    ok = snap.get("ok") is True
    iso = now.replace(microsecond=0).isoformat()
    if ok:
        stream = {
            "status": "healthy",
            "stream_state": "connected",
            "reason_code": "pyth_hermes_ok",
            "last_event_at": iso,
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
            "last_event_at": iso,
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
                "observed_at": iso,
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
    print(f"pyth_stream_probe: repo={_repo_root()} artifacts={art} interval={_INTERVAL}s", flush=True)
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
