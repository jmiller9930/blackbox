"""
Interpretation: trader-language → summary, signals, assumptions, concept tags (keyword v1).
"""
from __future__ import annotations

import re
from typing import Any

# Keyword → concept id (strings for concepts_used; registry wiring later)
CONCEPT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("liquidity", re.compile(r"\b(liquidity|thin\s+liquidity|market\s+depth|depth|order\s+book)\b", re.I)),
    ("spread", re.compile(r"\b(spread|spreads|bid[- ]ask|widening|wide\s+spread)\b", re.I)),
    ("slippage", re.compile(r"\b(slippage|slip)\b", re.I)),
    ("volatility", re.compile(r"\b(volatility|volatile|chop|choppy|swing)\b", re.I)),
    ("risk", re.compile(r"\b(risk|risky|danger|careful|caution)\b", re.I)),
    ("trend", re.compile(r"\b(trend|trending|momentum|breakout)\b", re.I)),
    ("volume", re.compile(r"\b(volume|liquidity\s+crunch)\b", re.I)),
]


def extract_concepts(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cid, pat in CONCEPT_PATTERNS:
        if pat.search(text) and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def build_interpretation(
    input_text: str,
    concepts: list[str],
    guardrail_mode: str,
    readiness: str | None,
) -> dict[str, Any]:
    signals = [f"concept:{c}" for c in concepts]
    if not signals:
        signals.append("no strong keyword match; interpret manually")

    assumptions = [
        "Rule-based v1 analyst — not predictive; does not call markets or execute.",
        "Concept tags are keyword-derived; not registry-backed in v1.",
    ]
    if readiness:
        assumptions.append(f"Decision context readiness (if loaded): {readiness}.")

    summary = (
        f"Interpreted trader concern as focusing on: {', '.join(concepts) or 'general market commentary'}. "
        f"Structured under current guardrail posture ({guardrail_mode})."
    )

    return {
        "summary": summary,
        "signals": signals,
        "assumptions": assumptions,
    }
