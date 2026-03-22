#!/usr/bin/env python3
"""
Phase 3.1 — Read-only market data ingestion: fetch → normalize → JSON (market_snapshot_v1).

No trading, wallets, execution, or venue writes. Optional --store as a completed tasks row.

Source chain (first success wins; all read-only, no API keys):
  1. Coinbase Exchange REST — product ticker (default SOL-USD); good US visibility.
  2. Kraken public Ticker — pair SOLUSD.
  3. Binance public — SOLUSDT (may be geo-restricted in some regions).
  4. CoinGecko simple/price — SOL/USD price/vol only (bid/ask null).

If Python cannot verify TLS (e.g. macOS without certifi bundle), all HTTPS calls fail —
fix the environment (Install Certificates.command) or use a host with proper CA store (e.g. clawbot).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root

SCHEMA_VERSION = 1
SOURCE_COINBASE = "coinbase_exchange_public_rest"
SOURCE_KRAKEN = "kraken_public_rest"
SOURCE_BINANCE = "binance_public_rest"
SOURCE_COINGECKO = "coingecko_public_rest"

USER_AGENT = "blackbox-market-data-ingestor/1.0 (+read-only)"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _http_get_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _fetch_coinbase(product_id: str) -> tuple[dict[str, Any] | None, list[str]]:
    """https://docs.cloud.coinbase.com/exchange/reference/exchangerestapi_getproductticker"""
    notes: list[str] = []
    pid = product_id.strip()
    url = f"https://api.exchange.coinbase.com/products/{pid}/ticker"
    try:
        data = _http_get_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        notes.append(f"Coinbase ticker failed: {type(e).__name__}: {e}")
        return None, notes

    bid, ask = _f(data.get("bid")), _f(data.get("ask"))
    last = _f(data.get("price"))
    vol = _f(data.get("volume"))
    spread = None
    if bid is not None and ask is not None and ask >= bid:
        spread = ask - bid

    base = pid.split("-")[0] if "-" in pid else pid

    out: dict[str, Any] = {
        "source": SOURCE_COINBASE,
        "market_symbol": pid,
        "asset": base,
        "price": last,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "volume": vol,
        "liquidity_depth_summary": None,
        "volatility_placeholder": None,
    }
    notes.append("Primary: Coinbase Exchange GET /products/{product_id}/ticker (read-only, no auth).")
    return out, notes


def _fetch_kraken() -> tuple[dict[str, Any] | None, list[str]]:
    notes: list[str] = []
    url = "https://api.kraken.com/0/public/Ticker?pair=SOLUSD"
    try:
        data = _http_get_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        notes.append(f"Kraken ticker failed: {type(e).__name__}: {e}")
        return None, notes

    err = data.get("error")
    if err:
        notes.append(f"Kraken API errors: {err}")
        return None, notes

    result = data.get("result")
    if not isinstance(result, dict) or not result:
        notes.append("Kraken: empty result.")
        return None, notes

    # Pair key is often SOLUSD
    tick = next(iter(result.values()))
    if not isinstance(tick, dict):
        return None, notes + ["Kraken: unexpected ticker shape."]

    a = tick.get("a")
    b = tick.get("b")
    c = tick.get("c")
    ask = _f(a[0]) if isinstance(a, list) and a else None
    bid = _f(b[0]) if isinstance(b, list) and b else None
    last = _f(c[0]) if isinstance(c, list) and c else None

    v = tick.get("v")
    vol = None
    if isinstance(v, list) and v:
        vol = _f(v[1]) if len(v) > 1 else _f(v[0])

    spread = None
    if bid is not None and ask is not None and ask >= bid:
        spread = ask - bid

    high = _f(tick.get("h", [None, None])[1] if isinstance(tick.get("h"), list) else None)
    low = _f(tick.get("l", [None, None])[1] if isinstance(tick.get("l"), list) else None)
    vol_ph = None
    if high is not None and low is not None and last is not None and last > 0:
        mid = (high + low) / 2.0
        rng = ((high - low) / mid) * 100.0 if mid > 0 else None
        vol_ph = {
            "basis": "kraken_24h_high_low_vs_last",
            "high_24h": high,
            "low_24h": low,
            "last": last,
            "range_pct_of_mid": round(rng, 6) if rng is not None else None,
        }

    out: dict[str, Any] = {
        "source": SOURCE_KRAKEN,
        "market_symbol": "SOLUSD",
        "asset": "SOL",
        "price": last,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "volume": vol,
        "liquidity_depth_summary": None,
        "volatility_placeholder": vol_ph,
    }
    notes.append("Fallback: Kraken GET /0/public/Ticker?pair=SOLUSD (read-only).")
    return out, notes


def _fetch_binance(symbol: str) -> tuple[dict[str, Any] | None, list[str]]:
    notes: list[str] = []
    sym = symbol.upper().strip()
    book_url = f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={sym}"
    day_url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}"

    try:
        book = _http_get_json(book_url)
        day = _http_get_json(day_url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        notes.append(f"Binance fetch failed: {type(e).__name__}: {e}")
        return None, notes

    # Geo / restriction: Binance may return JSON error object without bidPrice
    if "code" in book and "msg" in book and "bidPrice" not in book:
        notes.append(f"Binance unavailable or restricted: {book.get('msg', book)[:200]}")
        return None, notes

    bid_f = _f(book.get("bidPrice"))
    ask_f = _f(book.get("askPrice"))
    bid_q = _f(book.get("bidQty"))
    ask_q = _f(book.get("askQty"))

    last = _f(day.get("lastPrice"))
    spread = None
    if bid_f is not None and ask_f is not None and ask_f >= bid_f:
        spread = ask_f - bid_f

    high_24h = _f(day.get("highPrice"))
    low_24h = _f(day.get("lowPrice"))
    vol = _f(day.get("volume"))

    recent_movement: dict[str, Any] | None = None
    if high_24h is not None and low_24h is not None and last is not None and last > 0:
        mid = (high_24h + low_24h) / 2.0
        range_pct = ((high_24h - low_24h) / mid) * 100.0 if mid > 0 else None
        recent_movement = {
            "basis": "24h_high_low_vs_last",
            "high_24h": high_24h,
            "low_24h": low_24h,
            "last": last,
            "range_pct_of_mid": round(range_pct, 6) if range_pct is not None else None,
        }

    liquidity: dict[str, Any] | None = None
    if bid_q is not None or ask_q is not None:
        liquidity = {
            "top_of_book_bid_qty": bid_q,
            "top_of_book_ask_qty": ask_q,
            "interpretation": "shallow L1 only; not full order book depth",
        }

    asset_guess = sym.replace("USDT", "").replace("BUSD", "") if sym else "UNKNOWN"

    out: dict[str, Any] = {
        "source": SOURCE_BINANCE,
        "market_symbol": sym,
        "asset": asset_guess,
        "price": last,
        "bid": bid_f,
        "ask": ask_f,
        "spread": spread,
        "volume": vol,
        "liquidity_depth_summary": liquidity,
        "volatility_placeholder": recent_movement,
    }
    notes.append("Fallback: Binance public bookTicker + 24hr (may be geo-restricted).")
    return out, notes


def _fetch_coingecko_sol() -> tuple[dict[str, Any] | None, list[str]]:
    notes: list[str] = []
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=solana&vs_currencies=usd&include_24hr_vol=true&include_24hr_change=true"
    )
    try:
        data = _http_get_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        notes.append(f"CoinGecko fallback failed: {type(e).__name__}: {e}")
        return None, notes

    block = data.get("solana")
    if not isinstance(block, dict):
        notes.append("CoinGecko: unexpected payload shape for solana.")
        return None, notes

    price_f = _f(block.get("usd"))
    vol_f = _f(block.get("usd_24h_vol"))
    chg_f = _f(block.get("usd_24h_change"))

    out: dict[str, Any] = {
        "source": SOURCE_COINGECKO,
        "market_symbol": "SOL-USD",
        "asset": "SOL",
        "price": price_f,
        "bid": None,
        "ask": None,
        "spread": None,
        "volume": vol_f,
        "liquidity_depth_summary": None,
        "volatility_placeholder": (
            {"basis": "coingecko_24h_change_pct", "usd_24h_change_pct": chg_f}
            if chg_f is not None
            else None
        ),
    }
    notes.append("Last resort: CoinGecko simple/price (bid/ask explicitly null).")
    return out, notes


def build_snapshot(*, coinbase_product: str, binance_symbol: str) -> dict[str, Any]:
    """Return market_snapshot_v1 dict."""
    generated_at = _utc_now()
    all_notes: list[str] = []

    merged: dict[str, Any] | None = None

    m, n = _fetch_coinbase(coinbase_product)
    all_notes.extend(n)
    if m is not None:
        merged = m

    if merged is None:
        m, n = _fetch_kraken()
        all_notes.extend(n)
        if m is not None:
            merged = m

    if merged is None:
        m, n = _fetch_binance(binance_symbol)
        all_notes.extend(n)
        if m is not None:
            merged = m

    if merged is None:
        m, n = _fetch_coingecko_sol()
        all_notes.extend(n)
        if m is not None:
            merged = m

    if merged is None:
        return {
            "kind": "market_snapshot_v1",
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "source": "unavailable",
            "market_symbol": coinbase_product,
            "asset": None,
            "price": None,
            "bid": None,
            "ask": None,
            "spread": None,
            "volume": None,
            "liquidity_depth_summary": None,
            "volatility_placeholder": None,
            "notes": all_notes
            + [
                "DATA: all read-only sources failed — no fabricated values.",
                "If TLS errors: ensure system CA bundle (e.g. Python Install Certificates on macOS) or run on a host with valid HTTPS (e.g. clawbot).",
            ],
        }

    all_notes.append(
        "DATA: unreachable sources should surface clearly; optional future hook to system_health_logs."
    )
    return {
        "kind": "market_snapshot_v1",
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source": merged["source"],
        "market_symbol": merged["market_symbol"],
        "asset": merged["asset"],
        "price": merged["price"],
        "bid": merged["bid"],
        "ask": merged["ask"],
        "spread": merged["spread"],
        "volume": merged["volume"],
        "liquidity_depth_summary": merged["liquidity_depth_summary"],
        "volatility_placeholder": merged.get("volatility_placeholder"),
        "notes": all_notes,
    }


def run(db_path: Path | None, *, coinbase_product: str, binance_symbol: str, store: bool) -> int:
    snap = build_snapshot(coinbase_product=coinbase_product, binance_symbol=binance_symbol)
    out: dict[str, Any] = dict(snap)
    out["stored_task_id"] = None

    unreachable = snap.get("source") == "unavailable"
    if store:
        if unreachable:
            print(
                json.dumps(
                    {
                        **snap,
                        "stored_task_id": None,
                        "error": "store skipped: no snapshot data (all sources unreachable)",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 2
        root = repo_root()
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = snap["generated_at"]
        title = f"[Market Snapshot] {snap.get('market_symbol', 'UNKNOWN')} {now[:19]}Z"
        desc = json.dumps(snap, ensure_ascii=False, indent=2)
        conn.execute(
            """
            INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, "data", title, desc, "completed", "normal", now, now),
        )
        conn.commit()
        conn.close()
        out["stored_task_id"] = tid

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 2 if unreachable else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 3.1 — read-only market snapshot (market_snapshot_v1)",
    )
    p.add_argument(
        "--coinbase-product",
        default="SOL-USD",
        metavar="ID",
        help="Coinbase Exchange product id (default SOL-USD)",
    )
    p.add_argument(
        "--binance-symbol",
        default="SOLUSDT",
        metavar="PAIR",
        help="Binance spot pair if used in fallback chain (default SOLUSDT)",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: BLACKBOX_SQLITE_PATH or data/sqlite/blackbox.db)",
    )
    p.add_argument(
        "--store",
        action="store_true",
        help="Persist snapshot JSON as a completed [Market Snapshot] task row",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(
        db,
        coinbase_product=args.coinbase_product,
        binance_symbol=args.binance_symbol,
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
