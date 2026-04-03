"""Jupiter Quote API v6 — implied on-chain mid from a fixed SOL→USDC route (Phase 5.1+).

This is **not** a CEX ticker: it is the effective USDC received for a fixed SOL notional
via Jupiter's quoted route, expressed as USD per SOL for comparison with Pyth/Coinbase.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "blackbox-market-data/5.1 (+read-only)"
SOURCE = "jupiter_quote_v6"

# Mainnet canonical mints (fixed-route comparator; document in raw)
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Full path to v6 quote endpoint (override with JUPITER_QUOTE_API_URL)
DEFAULT_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
# Default: 1 SOL in lamports → implied USD/SOL from USDC out (6 decimals)
DEFAULT_IN_LAMPORTS = 1_000_000_000
DEFAULT_SLIPPAGE_BPS = 50


@dataclass(frozen=True)
class NormalizedQuote:
    source: str
    symbol: str
    price: float | None
    observed_at: str
    notes: list[str]
    raw: dict[str, Any]


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


def fetch_jupiter_implied_sol_usd(
    *,
    in_lamports: int = DEFAULT_IN_LAMPORTS,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    quote_url: str | None = None,
    timeout: float = 25.0,
) -> NormalizedQuote:
    """GET Jupiter v6 quote SOL→USDC; implied USD/SOL = USDC_out / SOL_in."""
    base = (quote_url or os.environ.get("JUPITER_QUOTE_API_URL") or DEFAULT_QUOTE_URL).strip()

    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    notes: list[str] = []
    params = {
        "inputMint": SOL_MINT,
        "outputMint": USDC_MINT,
        "amount": str(int(in_lamports)),
        "slippageBps": str(int(slippage_bps)),
    }
    url = f"{base.rstrip('/')}?{urlencode(params)}"
    notes.append("Jupiter v6 quote SOL→USDC (fixed route; implied USD/SOL).")

    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        notes.append(f"jupiter_quote_failed:{type(e).__name__}:{e}")
        return NormalizedQuote(
            source=SOURCE,
            symbol="SOL-USD",
            price=None,
            observed_at=observed_at,
            notes=notes,
            raw={"error": str(e), "request_url": url},
        )

    if not isinstance(raw, dict):
        notes.append("jupiter_invalid_payload")
        return NormalizedQuote(
            source=SOURCE,
            symbol="SOL-USD",
            price=None,
            observed_at=observed_at,
            notes=notes,
            raw={},
        )

    err = raw.get("error")
    if err:
        notes.append(f"jupiter_quote_error:{err}")
        return NormalizedQuote(
            source=SOURCE,
            symbol="SOL-USD",
            price=None,
            observed_at=observed_at,
            notes=notes,
            raw=dict(raw),
        )

    out_amt = raw.get("outAmount")
    out_i: int | None = None
    try:
        out_i = int(str(out_amt))
    except (TypeError, ValueError):
        out_i = None

    if out_i is None or out_i <= 0:
        notes.append("jupiter_missing_out_amount")
        return NormalizedQuote(
            source=SOURCE,
            symbol="SOL-USD",
            price=None,
            observed_at=observed_at,
            notes=notes,
            raw=dict(raw),
        )

    sol_in = float(in_lamports) / 1e9
    usdc_out = float(out_i) / 1e6
    if sol_in <= 0:
        notes.append("jupiter_nonpositive_sol_in")
        return NormalizedQuote(
            source=SOURCE,
            symbol="SOL-USD",
            price=None,
            observed_at=observed_at,
            notes=notes,
            raw=dict(raw),
        )

    implied = usdc_out / sol_in
    px = _f(implied)
    if px is None:
        notes.append("jupiter_implied_non_numeric")
        return NormalizedQuote(
            source=SOURCE,
            symbol="SOL-USD",
            price=None,
            observed_at=observed_at,
            notes=notes,
            raw=dict(raw),
        )

    enriched = dict(raw)
    enriched["_blackbox_implied_usd_per_sol"] = px
    enriched["_blackbox_in_lamports"] = int(in_lamports)
    enriched["_blackbox_out_amount_usdc_atomic"] = out_i

    return NormalizedQuote(
        source=SOURCE,
        symbol="SOL-USD",
        price=px,
        observed_at=observed_at,
        notes=notes,
        raw=enriched,
    )


__all__ = [
    "DEFAULT_IN_LAMPORTS",
    "DEFAULT_QUOTE_URL",
    "SOL_MINT",
    "USDC_MINT",
    "NormalizedQuote",
    "fetch_jupiter_implied_sol_usd",
]
