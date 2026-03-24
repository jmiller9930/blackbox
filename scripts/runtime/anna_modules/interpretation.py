"""
Interpretation: trader-language → summary, signals, assumptions, concept tags (keyword v1).

Phase 3.8: advanced strategy awareness (detection + advisory text only; not execution).
"""
from __future__ import annotations

import re
from typing import Any

# Awareness-only strategy ids (not registry-backed; advisory framing).
STRATEGY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("market_making", re.compile(
        r"\b(market\s+making|market[- ]making|market\s+maker)\b", re.I
    )),
    ("spread_capture", re.compile(
        r"\b(spread\s+capture|capture\s+(the\s+)?spread|harvest(ing)?\s+spread)\b", re.I
    )),
    ("inventory_risk", re.compile(
        r"\b(inventory\s+risk|inventory\s+imbalance)\b", re.I
    )),
    ("adverse_selection", re.compile(
        r"\b(adverse\s+selection|picked\s+off|getting\s+picked\s+off)\b", re.I
    )),
    ("liquidity_provision", re.compile(
        r"\b(liquidity\s+provision|provide\s+liquidity|liquidity\s+provider)\b", re.I
    )),
    ("order_book_dynamics", re.compile(
        r"\b(order\s+book\s+dynamics|thin\s+books?|thin\s+book|l2\s+dynamics)\b", re.I
    )),
]

STRATEGY_COPY: dict[str, str] = {
    "market_making": (
        "Market making involves quoting both sides to earn the bid–ask spread while managing "
        "inventory and adverse selection."
    ),
    "spread_capture": (
        "Spread capture strategies seek to earn the spread or rebates; edge depends on fees, "
        "latency, and stability of quotes."
    ),
    "inventory_risk": (
        "Inventory risk is exposure to directional moves while holding a net position from "
        "filled quotes or passive orders."
    ),
    "adverse_selection": (
        "Adverse selection arises when counterparties are better informed, so fills tend to "
        "move against you after the trade."
    ),
    "liquidity_provision": (
        "Liquidity provision means resting orders that others can hit; compensation is "
        "typically spread and/or rebates minus adverse movement."
    ),
    "order_book_dynamics": (
        "Order book dynamics cover depth, queue position, and how size and cancellations "
        "affect short-term price pressure."
    ),
}

STRATEGY_RISKS: dict[str, list[str]] = {
    "market_making": [
        "Inventory imbalance if flow is one-sided",
        "Adverse selection on stale quotes",
    ],
    "spread_capture": [
        "Spread can collapse under volatility",
        "Fees and latency can erase edge",
    ],
    "inventory_risk": [
        "Directional exposure while working orders",
        "Hedging costs and timing",
    ],
    "adverse_selection": [
        "Persistent adverse fills in informed flow",
        "Harder to detect in thin books",
    ],
    "liquidity_provision": [
        "Picked off during fast moves",
        "Queue and priority uncertainty",
    ],
    "order_book_dynamics": [
        "Thin depth increases impact",
        "Hidden size and cancels change apparent liquidity",
    ],
}


def detect_strategy_concepts(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for sid, pat in STRATEGY_PATTERNS:
        if pat.search(text) and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def build_strategy_awareness(
    input_text: str,
    *,
    price: float | None,
    spread: float | None,
    market_notes: list[str],
) -> dict[str, Any] | None:
    """
    Advisory-only: explanations and risks; no execution or strategy commands.
    Returns None when nothing detected (null-safe for JSON).
    """
    detected = detect_strategy_concepts(input_text)
    if not detected:
        return None

    explanations = [STRATEGY_COPY[s] for s in detected if s in STRATEGY_COPY]
    explanation = " ".join(explanations) if explanations else (
        "Advanced strategy language detected; treatment is descriptive only."
    )

    risks: list[str] = []
    seen_r: set[str] = set()
    for s in detected:
        for r in STRATEGY_RISKS.get(s, []):
            if r not in seen_r:
                seen_r.add(r)
                risks.append(r)

    parts: list[str] = []
    if spread is not None and price is not None and price > 0:
        bps = (spread / price) * 10000.0
        parts.append(f"Snapshot spread ≈ {bps:.1f} bps of mid (informational).")
    if re.search(r"\bthin\b", input_text, re.I):
        parts.append("Language references thin conditions; fills and impact deserve extra scrutiny.")
    if not parts:
        parts.append("Advisory framing only; applicability depends on venue, fees, and live book state.")

    applicability = " ".join(parts)

    return {
        "detected": detected,
        "explanation": explanation,
        "risks": risks,
        "applicability": applicability,
        "note": (
            "Strategy awareness is informational and analytical only; not a directive to trade "
            "or bypass policy."
        ),
    }


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
    *,
    registry_loaded: bool = False,
    human_intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Human-facing summary must read like an analyst, not an internal template.
    Guardrail/registry diagnostics go to assumptions (JSON / logs), not the lead sentence.
    """
    signals = [f"concept:{c}" for c in concepts]
    if not signals:
        signals.append("no strong keyword match; interpret manually")

    assumptions = [
        "Rule-based v1 analyst — not predictive; does not call markets or execute.",
    ]
    if registry_loaded and concepts:
        assumptions.append("Concept IDs matched against trading concept registry (read-only).")
    elif registry_loaded and not concepts:
        assumptions.append("No registry concept IDs matched this input; see concept_support and notes.")
    else:
        assumptions.append("Trading concept registry unavailable or invalid; concept_support empty.")
    if readiness:
        assumptions.append(f"Decision context readiness (if loaded): {readiness}.")
    assumptions.append(f"Internal guardrail mode for policy: {guardrail_mode}.")

    topic = (human_intent or {}).get("topic")
    intent = (human_intent or {}).get("intent")

    if topic == "exit_logic":
        headline = "Exit timing"
        summary = (
            "You're asking how to exit when a trade is still working but price looks extended or ready to "
            "roll over. Below is how I'd think about risk, profit protection, and reversal signals — "
            "advisory only, not a buy/sell instruction."
        )
    elif topic == "trading_general" and concepts:
        headline = "Your question"
        summary = (
            f"I'm reading this around: {', '.join(concepts)}. I'll walk through risk and what I'd watch — "
            "still advisory, not execution."
        )
    elif topic == "feedback" or intent == "CORRECTION":
        headline = "Feedback"
        summary = (
            "Sounds like you're correcting or challenging a prior read — I'll take that seriously and "
            "focus on what would have changed the view."
        )
    elif intent == "INSTRUCTION":
        headline = "Instruction"
        summary = (
            "You're steering toward a rule or habit — I'll respond in terms of risk and process, not "
            "automated execution."
        )
    elif intent == "OBSERVATION":
        headline = "Observation"
        summary = (
            "You're sharing a market read — I'll reflect it back with structure and what I'd validate next."
        )
    elif concepts:
        headline = "Your question"
        summary = (
            f"I'm reading this around: {', '.join(concepts)}. I'll keep the answer practical and flag "
            "what we can't know from text alone."
        )
    else:
        headline = "Your question"
        summary = (
            "I'm treating this as a trading conversation without tight keyword tags; I'll keep the answer "
            "practical and name what we don't know from here."
        )

    return {
        "headline": headline,
        "summary": summary,
        "signals": signals,
        "assumptions": assumptions,
    }
