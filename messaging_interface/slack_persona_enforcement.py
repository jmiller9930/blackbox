"""
Directive 4.6.3.4.B.2 — deterministic Slack outbound persona enforcement.

Runs after model (or formatter) output, before posting to Slack.
Soft prompts may suggest tone; identity and forbidden phrases are enforced here.
"""

from __future__ import annotations

import re
from typing import Final

SLACK_AGENT_PREFIX: Final[str] = "[BlackBox — System Agent]"
ANNA_SLACK_STATUS: Final[str] = "Anna is not connected to Slack in this environment."

# Claims about Anna availability / reachability not backed by a real health integration.
_ANNA_STATUS_PATTERN = re.compile(
    r"(?is)"
    r"(?:^|\s)"
    r"(?:"
    r"Anna\s+is\s+(?:still\s+)?(?:offline|online)\b[^.!?\n]*[.!?]?"
    r"|Anna\s+is\s+(?:unavailable|not\s+available|unreachable|inactive|active|reachable)\b[^.!?\n]*[.!?]?"
    r"|Anna\s+is\s+(?:here|there|down|up)\b[^.!?\n]*[.!?]?"
    r"|Since\s+Anna\s+is\s+(?:offline|online|unavailable)\b[^.!?\n]*[.!?]?"
    r"|Because\s+Anna\s+is\s+(?:offline|online)\b[^.!?\n]*[.!?]?"
    r")",
)

_ANNA_IMPERSONATION = re.compile(
    r"(?i)\b(?:I\s+am\s+Anna|I'?m\s+Anna|this\s+is\s+Anna)\b[^.!?\n]*[.!?]?",
)

_FORBIDDEN_ANNA_TAG = "[Anna — Trading Analyst]"

# Extra literal patterns (regex) for variants the block regex can miss.
_ANNA_EXTRA = [
    re.compile(r"\bAnna\s+is\s+still\s+offline\b[^.!?\n]*[.!?]?", re.I),
    re.compile(r"\bAnna\s+is\s+still\s+online\b[^.!?\n]*[.!?]?", re.I),
]


def enforce_slack_outbound(raw: str) -> tuple[str, list[str]]:
    """
    Apply mandatory Slack persona rules. Returns (final_text, rules_triggered).
    """
    triggered: list[str] = []
    text = (raw or "").strip()
    if not text:
        out = f"{SLACK_AGENT_PREFIX}\n"
        triggered.append("empty_input_prefixed")
        return out, triggered

    if _FORBIDDEN_ANNA_TAG in text:
        text = text.replace(_FORBIDDEN_ANNA_TAG, "").strip()
        triggered.append("strip_anna_analyst_tag")

    if _ANNA_IMPERSONATION.search(text):
        text = _ANNA_IMPERSONATION.sub(
            "This reply is from the system agent, not Anna.",
            text,
        ).strip()
        triggered.append("strip_anna_impersonation")

    if _ANNA_STATUS_PATTERN.search(text):
        text = _ANNA_STATUS_PATTERN.sub(ANNA_SLACK_STATUS, text)
        triggered.append("replace_anna_status_claims")

    for ex in _ANNA_EXTRA:
        if ex.search(text):
            text = ex.sub(ANNA_SLACK_STATUS, text)
            triggered.append("replace_anna_status_extra")

    while ANNA_SLACK_STATUS + " " + ANNA_SLACK_STATUS in text:
        text = text.replace(ANNA_SLACK_STATUS + " " + ANNA_SLACK_STATUS, ANNA_SLACK_STATUS)
        triggered.append("dedupe_anna_sentence")

    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if not text.startswith(SLACK_AGENT_PREFIX):
        text = f"{SLACK_AGENT_PREFIX}\n\n{text}"
        triggered.append("prepend_identity_prefix")
    else:
        triggered.append("identity_prefix_already_present")

    return text, triggered
