"""
Directive 4.6.3 — classify human messages before Anna replies (QUESTION / OBSERVATION / INSTRUCTION / CORRECTION).

Rule-based only; no ML. Used to route phrasing and factual bypasses (e.g. calendar questions).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def classify_human_intent(text: str) -> dict[str, Any]:
    """
    Returns intent, optional topic, requires_reasoning, optional bypass kind.
    """
    raw = (text or "").strip()
    low = raw.lower()

    # Factual / non-market bypass (avoid fake "general market commentary" on these)
    if _is_factual_datetime_question(low):
        return {
            "intent": "QUESTION",
            "topic": "factual_datetime",
            "requires_reasoning": False,
            "bypass": "datetime",
        }

    if _looks_like_exit_timing_question(low):
        return {
            "intent": "QUESTION",
            "topic": "exit_logic",
            "requires_reasoning": True,
            "bypass": None,
        }

    if _looks_like_correction(low):
        return {"intent": "CORRECTION", "topic": "feedback", "requires_reasoning": True, "bypass": None}

    if _looks_like_instruction(low):
        return {"intent": "INSTRUCTION", "topic": "directive", "requires_reasoning": True, "bypass": None}

    if _looks_like_observation(low):
        return {"intent": "OBSERVATION", "topic": "market_observation", "requires_reasoning": True, "bypass": None}

    if "?" in raw or re.match(
        r"^\s*(how|what|why|when|where|who|should|could|would|is|are|do|does|can)\b",
        low,
    ):
        return {"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": True, "bypass": None}

    return {"intent": "OBSERVATION", "topic": "general", "requires_reasoning": True, "bypass": None}


def _is_factual_datetime_question(low: str) -> bool:
    if re.search(r"\bwhat\s+(day|date)\s+(is\s+it|today)\b", low):
        return True
    if re.search(r"\bwhat\s+time\s+(is\s+it|now)\b", low):
        return True
    if low.strip(" ?") in ("what day is it", "what's today's date", "todays date", "today's date"):
        return True
    return False


def _looks_like_exit_timing_question(low: str) -> bool:
    return bool(
        re.search(
            r"\b(get\s+out|exit|exiting|take\s+profit|stop\s+out|scale\s+out|trim|topping|topped|"
            r"reverse|reversal|give\s+back|stuck\s+in|when\s+to\s+sell|when\s+to\s+close)\b",
            low,
        )
    )


def _looks_like_correction(low: str) -> bool:
    return bool(re.search(r"\b(wrong|incorrect|that\s+was\s+wrong|bad\s+signal|because\s+volume)\b", low))


def _looks_like_instruction(low: str) -> bool:
    return bool(re.search(r"\b(we\s+should|let\'?s\s+|avoid\s+|don\'?t\s+trade|must\s+)\b", low)) and "?" not in low


def _looks_like_observation(low: str) -> bool:
    return bool(re.search(r"\b(looks?\s+fake|breakout|feels\s+weak|choppy|thin)\b", low)) and "?" not in low


def factual_datetime_answer() -> str:
    """UTC date/time for 'what day is it' style questions."""
    now = datetime.now(timezone.utc)
    return now.strftime("%A, %Y-%m-%d (UTC)")


def factual_time_answer() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%H:%M UTC")


def build_factual_reply(text: str) -> str | None:
    low = text.strip().lower()
    if re.search(r"\bwhat\s+time\b", low):
        return (
            f"The time I have here is {factual_time_answer()} "
            f"(server UTC — say your timezone if you need local wall clock)."
        )
    if _is_factual_datetime_question(low):
        return (
            f"Today is {factual_datetime_answer()} "
            f"(server UTC — check your device for local date if you're near midnight)."
        )
    return None
