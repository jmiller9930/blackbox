"""Deterministic live-data question detection for Anna grounding v1."""

from __future__ import annotations

import re

_RE_CONCEPT_ONLY = re.compile(
    r"\b(what\s+is\s+(a\s+)?spread|explain\s+(spread|liquidity|slippage)|what\s+is\s+slippage)\b",
    re.IGNORECASE,
)
_RE_LIVE_CUES = re.compile(
    r"\b(current|live|right\s+now)\b|\b(price|spread)\s+(of|on)\b|\btrading\s+at\b",
    re.IGNORECASE,
)
_RE_SPREAD_CUES = re.compile(r"\bspread\b", re.IGNORECASE)
_RE_TICKER = re.compile(r"\$?([A-Za-z]{2,10})(?:USDT)?\b")

_COIN_NAME_TO_SYMBOL: dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "ripple": "XRP",
    "dogecoin": "DOGE",
}


def requires_live_data(question: str) -> bool:
    text = (question or "").strip()
    if not text:
        return False
    low = text.lower()
    if _RE_CONCEPT_ONLY.search(low):
        return False
    return bool(_RE_LIVE_CUES.search(low))


def wants_spread(question: str) -> bool:
    return bool(_RE_SPREAD_CUES.search((question or "").lower()))


def extract_symbol(question: str) -> str:
    text = (question or "").strip()
    if not text:
        return ""
    low = text.lower()
    for coin_name, symbol in _COIN_NAME_TO_SYMBOL.items():
        if re.search(rf"\b{re.escape(coin_name)}\b", low):
            return symbol
    candidates = []
    for m in _RE_TICKER.finditer(text):
        c = m.group(1).upper()
        if c.endswith("USDT"):
            c = c[:-4]
        candidates.append(c)
    skip = {"WHAT", "IS", "THE", "CURRENT", "PRICE", "SPREAD", "LIVE", "ON", "OF", "TRADING", "AT", "ANNA"}
    for c in candidates:
        if c not in skip and len(c) <= 6:
            return c
    return ""
