#!/usr/bin/env python3
"""
POST sequential-learning tick on an interval (Docker sidecar next to api).

Requires sequential learning to be in ``running`` state; when idle, API returns quickly.
Env: BLACKBOX_API_TICK_URL (default http://api:8080/api/v1/sequential-learning/control/tick)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://api:8080/api/v1/sequential-learning/control/tick"


def main() -> None:
    url = (os.environ.get("BLACKBOX_API_TICK_URL") or DEFAULT_URL).strip()
    interval = float(os.environ.get("SEQUENTIAL_TICK_INTERVAL_SEC") or "5")
    max_ev = int(os.environ.get("SEQUENTIAL_TICK_MAX_EVENTS") or "5")
    print(f"sequential_http_tick_loop: url={url} interval={interval}s max_events={max_ev}", flush=True)
    while True:
        body = json.dumps({"max_events": max_ev}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8", errors="replace")[:500]
                print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), raw[:200], flush=True)
        except urllib.error.HTTPError as e:
            print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "HTTP", e.code, flush=True)
        except OSError as e:
            print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ERR", e, flush=True)
        time.sleep(max(1.0, interval))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
