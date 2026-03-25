"""
Slack outbound persona enforcement (4.6.3.4.B.2 + 4.6.3.4.C routing-aware).

Runs after model / formatter output, before posting to Slack.
"""

from __future__ import annotations

import re
from typing import Final, Literal

Route = Literal["system", "anna"]

SLACK_AGENT_PREFIX: Final[str] = "[BlackBox — System Agent]"
ANNA_HEADER: Final[str] = "[Anna — Trading Analyst]"
ANNA_SLACK_STATUS: Final[str] = "Anna is not connected to Slack in this environment."

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

_ANNA_EXTRA = [
    re.compile(r"\bAnna\s+is\s+still\s+offline\b[^.!?\n]*[.!?]?", re.I),
    re.compile(r"\bAnna\s+is\s+still\s+online\b[^.!?\n]*[.!?]?", re.I),
]

_MARKET_LIKE_OUTPUT = re.compile(
    r"(?is)"
    r"(?:\$\s?\d[\d,]*(?:\.\d+)?\b|"
    r"\b(?:price|spread)\b.{0,80}\b(?:approximately|approx|around|about|range)\b|"
    r"\b(?:current|live)\s+(?:price|spread)\b)"
)


def _apply_global_truth_and_status(text: str, triggered: list[str], *, strip_impersonation: bool) -> str:
    """Shared: forbidden availability claims; optional impersonation strip (system route only)."""
    if strip_impersonation and _ANNA_IMPERSONATION.search(text):
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

    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _contains_market_like_output(text: str) -> bool:
    return bool(_MARKET_LIKE_OUTPUT.search(text or ""))


def enforce_slack_outbound(raw: str, *, route: Route = "system") -> tuple[str, list[str]]:
    """
    Apply Slack persona rules. Returns (final_text, rules_triggered).

    - route=\"system\": require [BlackBox — System Agent]; strip Anna analyst tag from model mistakes.
    - route=\"anna\": require [Anna — Trading Analyst] (4.6.3.4.C real Anna path); never add BlackBox prefix.
    """
    triggered: list[str] = []
    text = (raw or "").strip()

    if route == "anna":
        if not text:
            out = f"{ANNA_HEADER}\n"
            triggered.append("empty_input_anna_header")
            return out, triggered
        # Drop mistaken system prefix
        if text.startswith(SLACK_AGENT_PREFIX):
            text = text[len(SLACK_AGENT_PREFIX) :].lstrip()
            triggered.append("strip_blackbox_prefix_anna_route")
        text = _apply_global_truth_and_status(text, triggered, strip_impersonation=False)
        if not text.startswith(ANNA_HEADER):
            text = f"{ANNA_HEADER}\n\n{text}"
            triggered.append("prepend_anna_header")
        else:
            triggered.append("anna_header_already_present")
        return text, triggered

    # --- system route (default) ---
    if not text:
        out = f"{SLACK_AGENT_PREFIX}\n"
        triggered.append("empty_input_prefixed")
        return out, triggered

    if _FORBIDDEN_ANNA_TAG in text:
        text = text.replace(_FORBIDDEN_ANNA_TAG, "").strip()
        triggered.append("strip_anna_analyst_tag")

    text = _apply_global_truth_and_status(text, triggered, strip_impersonation=True)
    if _contains_market_like_output(text):
        text = "Hello — how can I help?"
        triggered.append("block_ungrounded_market_like_output")

    if not text.startswith(SLACK_AGENT_PREFIX):
        text = f"{SLACK_AGENT_PREFIX}\n\n{text}"
        triggered.append("prepend_identity_prefix")
    else:
        triggered.append("identity_prefix_already_present")

    return text, triggered
