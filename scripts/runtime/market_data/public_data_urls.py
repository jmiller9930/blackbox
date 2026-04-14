"""
Canonical **HTTPS origins** and paths for **Pyth Hermes** and **Binance public REST**.

Aligned with ``scripts/trading/pyth_sse_ingest.py``, ``preflight_pyth_tui.py``, and
``vscode-test/seanv3/``. See ``VPN/README.md``: on clawbot, **Binance** traffic to
``api.binance.com`` may be policy-routed via host WireGuard; **Hermes** uses the
normal public path (not forced through the Binance tunnel). Application code keeps
the same URL shape everywhere; **routing** is a host concern.

Environment (optional — **origin only**, scheme + host, no path; trailing ``/`` stripped):

- ``PYTH_HERMES_BASE_URL`` — default ``https://hermes.pyth.network``
- ``HERMES_PYTH_BASE_URL`` — alias
- ``BINANCE_API_BASE_URL`` — default ``https://api.binance.com``
- ``BINANCE_REST_BASE_URL`` — alias

Fixed paths (Hermes REST/SSE, Binance REST) match public API docs and existing callers.
"""

from __future__ import annotations

import os
import urllib.parse

_DEFAULT_HERMES = "https://hermes.pyth.network"
_DEFAULT_BINANCE = "https://api.binance.com"


def pyth_hermes_origin() -> str:
    raw = (
        os.environ.get("PYTH_HERMES_BASE_URL")
        or os.environ.get("HERMES_PYTH_BASE_URL")
        or ""
    ).strip()
    return (raw or _DEFAULT_HERMES).rstrip("/")


def binance_api_origin() -> str:
    raw = (
        os.environ.get("BINANCE_API_BASE_URL")
        or os.environ.get("BINANCE_REST_BASE_URL")
        or ""
    ).strip()
    return (raw or _DEFAULT_BINANCE).rstrip("/")


def hermes_price_latest_parsed_url(feed_id: str) -> str:
    """Hermes REST: latest feed update with ``parsed=true`` (operator preflight, probes)."""
    fid = (feed_id or "").strip()
    base = pyth_hermes_origin()
    # Hermes expects ``ids[]`` — keep literal query shape used across the repo.
    return f"{base}/v2/updates/price/latest?ids[]={urllib.parse.quote(fid, safe='')}&parsed=true"


def hermes_price_stream_url(feed_id: str) -> str:
    """Hermes SSE: ``/v2/updates/price/stream`` (``pyth_sse_ingest``, sandboxes)."""
    fid = (feed_id or "").strip()
    base = pyth_hermes_origin()
    return f"{base}/v2/updates/price/stream?ids[]={urllib.parse.quote(fid, safe='')}"


def binance_ping_url() -> str:
    return f"{binance_api_origin()}/api/v3/ping"


def binance_klines_url(
    *,
    symbol: str = "SOLUSDT",
    interval: str = "5m",
    limit: int = 1,
    extra_query: dict[str, str | int] | None = None,
) -> str:
    """Binance spot klines (Sean baseline / volume / preflight smoke)."""
    q: dict[str, str] = {
        "symbol": (symbol or "SOLUSDT").strip().upper(),
        "interval": (interval or "5m").strip(),
        "limit": str(max(1, int(limit))),
    }
    if extra_query:
        for k, v in extra_query.items():
            q[str(k)] = str(v)
    qs = urllib.parse.urlencode(q)
    return f"{binance_api_origin()}/api/v3/klines?{qs}"
