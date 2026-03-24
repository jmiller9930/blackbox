"""
Directive 4.6.3.X — Context completeness checker.
Determines whether a question has enough context to answer safely.
"""
from __future__ import annotations

import re
from typing import Any


def assess_context_completeness(text: str) -> dict[str, Any]:
    """
    Returns whether the question has sufficient context.
    If not, provides a clarifying question.
    """
    raw = (text or "").strip()
    low = raw.lower()

    missing: list[str] = []
    clarifying = None

    # Check for live trade indicators vs general question
    has_symbol = bool(re.search(r"\b(sol|btc|eth|perp|sol-perp|btc-perp)\b", low))
    has_timeframe = bool(re.search(r"\b(5m|15m|1h|4h|daily|5min)\b", low))
    has_live_indicators = bool(re.search(r"\b(live|now|current|this trade|my position|should we take it)\b", low))

    is_ambiguous = has_live_indicators and not (has_symbol or has_timeframe)

    if is_ambiguous:
        missing.append("question_mode")
        missing.append("symbol")
        if not has_timeframe:
            missing.append("timeframe")
        clarifying = "Are you asking generally, or about a live trade right now? If live, what symbol and timeframe are we talking about?"

    elif (
        ("should we take it" in low or "should i take" in low)
        and not (has_symbol or has_timeframe)
    ):
        missing.append("context")
        missing.append("symbol")
        missing.append("timeframe")
        clarifying = "Can you give me more context? What symbol, timeframe, and current conditions are we looking at?"

    is_complete = len(missing) == 0

    return {
        "is_complete": is_complete,
        "missing_fields": missing,
        "clarifying_question": clarifying,
        "requires_clarification": not is_complete,
    }
