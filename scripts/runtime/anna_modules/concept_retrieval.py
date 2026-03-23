"""
Phase 3.6 — Read-only concept detection + selective registry retrieval.

Uses `data/concepts/registry.json` via `concept_registry_reader.load_registry`.
Does not load the full registry into Anna output—only matched entries as concise summaries.
"""
from __future__ import annotations

import re
from typing import Any

from concept_registry_reader import find_concept, load_registry

# Registry `concept_id` → regex for trader language (order: first pass wins; dedupe preserves order).
DETECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("liquidity", re.compile(r"\b(liquidity|illiquid|thin\s+liquidity)\b", re.I)),
    ("spread", re.compile(r"\b(spread|spreads|bid[- ]ask|widening|wide\s+spread)\b", re.I)),
    ("slippage", re.compile(r"\b(slippage|slip)\b", re.I)),
    ("depth", re.compile(r"\b(depth|market\s+depth|order\s+book|book\s+depth)\b", re.I)),
    ("volatility", re.compile(r"\b(volatility|volatile|chop|choppy|swing)\b", re.I)),
    ("volume", re.compile(r"\b(volume|turnover)\b", re.I)),
    ("price", re.compile(r"\b(price|priced|mid\s+price)\b", re.I)),
    ("bid", re.compile(r"\bbid\b", re.I)),
    ("ask", re.compile(r"\bask\b", re.I)),
    ("market_order", re.compile(r"\bmarket\s+order\b", re.I)),
    ("limit_order", re.compile(r"\blimit\s+order\b", re.I)),
    ("candle", re.compile(r"\b(candle|candlestick|ohlc)\b", re.I)),
    ("timeframe", re.compile(r"\b(timeframe|time\s+frame|1m|5m|15m|1h|4h|1d)\b", re.I)),
    ("price_impact", re.compile(r"\b(price\s+impact|market\s+impact)\b", re.I)),
    ("maker_taker", re.compile(r"\b(maker|taker|post[- ]only)\b", re.I)),
]


def _concept_index(concepts: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in concepts:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("concept_id", "")).lower()
        if cid:
            out[cid] = c
    return out


def detect_registry_concept_ids(input_text: str, concepts: list[dict[str, Any]]) -> list[str]:
    """Return ordered unique concept_ids that match language AND exist in registry."""
    by_id = _concept_index(concepts)
    matched: list[str] = []
    seen: set[str] = set()
    for cid, pat in DETECTION_PATTERNS:
        if cid not in by_id:
            continue
        if pat.search(input_text) and cid not in seen:
            if find_concept(concepts, cid) is not None:
                matched.append(cid)
                seen.add(cid)
    return matched


def build_concept_summaries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Concise summaries only — not full registry rows."""
    out: list[dict[str, Any]] = []
    for c in entries:
        wim = c.get("why_it_matters", "")
        if isinstance(wim, list):
            wim_list = [str(x).strip() for x in wim if str(x).strip()][:2]
        else:
            s = str(wim).strip()
            wim_list = [s[:400] + ("…" if len(s) > 400 else "")] if s else []
        out.append(
            {
                "concept_id": c.get("concept_id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "why_it_matters": wim_list,
            }
        )
    return out


def retrieve_concept_support(
    input_text: str,
) -> tuple[list[str], dict[str, Any], list[str], bool]:
    """
    Return (concepts_used_ids, concept_support dict, extra_notes, registry_loaded_ok).

    On registry error: empty ids, empty support, notes explain, registry_loaded_ok False.
    """
    notes: list[str] = []
    reg = load_registry()
    if "error" in reg:
        notes.append(f"Trading concept registry unavailable ({reg.get('error')}); concept_support empty.")
        return [], {"concept_ids": [], "concept_summaries": []}, notes, False

    concepts = reg.get("concepts")
    if not isinstance(concepts, list):
        notes.append("Registry concepts list invalid; concept_support empty.")
        return [], {"concept_ids": [], "concept_summaries": []}, notes, False

    ids = detect_registry_concept_ids(input_text, concepts)
    if not ids:
        notes.append("No registry-backed concepts matched trader input (read-only detection).")

    rows = [find_concept(concepts, i) for i in ids]
    rows = [r for r in rows if r is not None]
    support = {
        "concept_ids": ids,
        "concept_summaries": build_concept_summaries(rows),
    }
    return ids, support, notes, True
