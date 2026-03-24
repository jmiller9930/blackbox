"""
Educational / definition-style questions — read from the trading concept registry (git-versioned).

Used when LLM is unavailable or returns no layer, so "what is a spread?" still gets a correct answer
without inventing a web scraper.
"""
from __future__ import annotations

import re

from concept_registry_reader import find_concept, load_registry

_DEFINITION_RE = re.compile(
    r"^\s*(what\s+is|what\'s|what\s+are|define|definition\s+of|explain)\s+",
    re.I,
)

# "What is the spread on SOL?" — live quote, not a textbook definition
_LIVE_QUOTE_RE = re.compile(
    r"\b(what\s+is|what\'s)\s+(the\s+)?(spread|bid|ask)\s+(on|for)\s+",
    re.I,
)


def looks_like_definition_question(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if _LIVE_QUOTE_RE.search(raw):
        return False
    return bool(_DEFINITION_RE.match(raw))


def build_registry_definition_summary(
    input_text: str,
    concept_ids: list[str],
) -> tuple[str | None, str | None]:
    """
    Return (summary, headline) from registry rows for definition-style questions.
    """
    if not concept_ids or not looks_like_definition_question(input_text):
        return None, None
    reg = load_registry()
    if "error" in reg:
        return None, None
    concepts = reg.get("concepts")
    if not isinstance(concepts, list):
        return None, None

    blocks: list[str] = []
    headlines: list[str] = []
    for cid in concept_ids[:6]:
        row = find_concept(concepts, cid)
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("concept_id") or cid)
        defin = str(row.get("definition") or "").strip()
        tm = str(row.get("trader_meaning") or "").strip()
        wim = row.get("why_it_matters")
        if isinstance(wim, list):
            wim_s = "; ".join(str(x).strip() for x in wim[:2] if str(x).strip())
        else:
            wim_s = str(wim or "").strip()

        lines: list[str] = []
        if defin:
            lines.append(f"{name} — {defin}")
        if tm:
            lines.append(f"Practically: {tm}")
        if wim_s:
            lines.append(f"Why it matters: {wim_s}")
        ex = row.get("examples")
        if isinstance(ex, list) and ex:
            lines.append(f"Example: {ex[0]}")
        if lines:
            blocks.append(" ".join(lines))
            headlines.append(name)

    if not blocks:
        return None, None
    summary = "\n\n".join(blocks)
    headline = headlines[0] if headlines else "Concept"
    return summary, headline


def registry_facts_for_prompt(concept_ids: list[str]) -> list[str]:
    """Authoritative FACT lines for the LLM from registry definitions (no hallucination)."""
    if not concept_ids:
        return []
    reg = load_registry()
    if "error" in reg:
        return []
    concepts = reg.get("concepts")
    if not isinstance(concepts, list):
        return []
    out: list[str] = []
    for cid in concept_ids[:6]:
        row = find_concept(concepts, cid)
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("concept_id") or cid)
        defin = str(row.get("definition") or "").strip()
        tm = str(row.get("trader_meaning") or "").strip()
        if defin:
            out.append(f"FACT (registry): {name} — {defin}")
        if tm:
            out.append(f"FACT (registry): {name} — practical read: {tm}")
    return out
