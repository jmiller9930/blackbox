"""Validate LLM text before showing to users."""
from __future__ import annotations

FORBIDDEN_SUBSTR = (
    "guardrail mode unknown",
    "i'll walk through risk and what i'd watch",
    "without tight keyword tags",
)


def validate_llm_output(text: str) -> tuple[bool, str]:
    t = (text or "").strip()
    if len(t) < 12:
        return False, "too_short"
    if len(t) > 8000:
        return False, "too_long"
    low = t.lower()
    for f in FORBIDDEN_SUBSTR:
        if f in low:
            return False, f"forbidden:{f}"
    return True, "ok"
