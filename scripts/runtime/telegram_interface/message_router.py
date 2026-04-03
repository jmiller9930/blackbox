"""Parse Telegram text into a structured route (single bot, multi-agent personas)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

AgentId = Literal["anna", "data", "cody", "mia", "identity"]


@dataclass(frozen=True)
class RoutedMessage:
    """Primary agent + text. For DATA, data_mode selects report / insights / status."""

    agent: AgentId
    text: str
    data_mode: str | None = None  # report | insights | status | infra | None (general @data text)
    hashtag_tokens: tuple[str, ...] | None = None  # pure-hashtag operator lines (#status #system)


def _norm_phrase(s: str) -> str:
    t = (s or "").strip().lower()
    if t.endswith("?"):
        t = t[:-1].strip()
    return t


def _identity_intent_from_text(t: str) -> str | None:
    low = _norm_phrase(t)
    if low == "help":
        return "help"
    if low == "who are you":
        return "who"
    if low == "what can you do":
        return "capabilities"
    if low == "how do i use this":
        return "how"
    return None


def _parse_data_remainder(rest: str) -> tuple[str | None, str]:
    r = (rest or "").strip()
    low = _norm_phrase(r)
    if not r:
        return ("status", "")
    if low == "report":
        return ("report", "")
    if low == "insights":
        return ("insights", "")
    if low == "status":
        return ("status", "")
    if low == "infra":
        return ("infra", "")
    return (None, r)


_CODY_LEAD = re.compile(
    r"^\s*cody\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Natural-language → DATA (reporting / system state / insights / connectivity) — conservative vs trading education.
_RE_NL_DATA_STATUS = re.compile(
    r"(?:^|\b)((system|execution)\s+(status|state)|"
    r"(what|what's|whats)\s+(is\s+)?(the\s+)?(system|execution)\s+status|"
    r"\b(last\s+completed\s+phase|proof\s+required|proof\s+status|execution\s+context)\b|"
    r"\bphase\s+status\b|"
    r"\b(connectivity|reachability|uptime|service\s+health|node\s+health)\b)",
    re.IGNORECASE,
)
_RE_NL_DATA_REPORT = re.compile(
    r"\b((show|give|get|send)\s+(me\s+)?(the\s+)?report|"
    r"(summarize|summary)\s+(of\s+)?(the\s+)?(report|execution\s+feedback)|"
    r"\bhow\s+many\s+.*(execution|feedback)|"
    r"\bexecution\s+feedback\s+(summary|report|totals?))\b",
    re.IGNORECASE,
)
_RE_NL_DATA_INSIGHTS = re.compile(
    r"\b((show|give|get|send|list)\s+(me\s+)?(the\s+)?insights?|"
    r"insight\s+rows|rows?\s+of\s+insights)\b",
    re.IGNORECASE,
)
# Infrastructure / DB / SQL → DATA (live read-only snapshot on the bot host).
_RE_NL_DATA_INFRA = re.compile(
    r"\b(sqlite|sqlite3|blackbox\.db|\.db\b|"
    r"the\s+database|the\s+db\b|"
    r"\bsql\b|"
    r"system_events|"
    r"what\s+tables|list\s+tables|table\s+names|"
    r"infrastructure|telemetry|"
    r"how\s+many\s+rows|row\s+count|"
    r"schema\b|"
    r"what('s|s| is)\s+(in|inside)\s+(the\s+)?(sqlite|database|db))\b",
    re.IGNORECASE,
)

# Natural-language → Cody (engineering / repo / code) — must not catch trading education.
_RE_NL_CODY = re.compile(
    r"(?:^|\b)("
    r"refactor|github|pull request|codebase|\brepo\b|architecture|deploy|pipeline|"
    r"pytest|unit tests?|stack trace|stacktrace|dockerfile|kubernetes|\bk8s\b|"
    r"ci/cd|jenkins|telegram_interface|scripts/runtime|"
    r"\.py\b|package\.json|requirements\.txt|"
    r"bug\s+in\s+the\s+(code|script|repo|bot)|"
    r"how\s+do\s+i\s+(fix|patch|change)\s+the\s+(code|script|repo)|"
    r"(code|coding)\s+(change|review|quality)|"
    r"system\s+improvement\s+(for\s+)?(the\s+)?(code|repo|build|pipeline)"
    r")\b",
    re.IGNORECASE,
)


def _nl_data_mode(text: str) -> str | None:
    """If text is clearly about reporting / system state / insights / infra, return DATA mode."""
    if _RE_NL_DATA_INFRA.search(text):
        return "infra"
    if _RE_NL_DATA_STATUS.search(text):
        return "status"
    if _RE_NL_DATA_INSIGHTS.search(text):
        return "insights"
    if _RE_NL_DATA_REPORT.search(text):
        return "report"
    return None


def _nl_looks_like_cody(text: str) -> bool:
    """Engineering / repo / code / architecture — not market education."""
    return bool(_RE_NL_CODY.search(text))


# Composable operator hashtags — message is *only* #tokens (whitespace between).
# See docs/runtime/slack_hashtag_language.md (grammar: #status #system = full stack).
_PURE_HASHTAG_LINE = re.compile(r"^(\s*#[\w-]+\s*)+$", re.IGNORECASE)


def _extract_hashtag_tokens(text: str) -> list[str] | None:
    raw = (text or "").strip()
    if not raw or not _PURE_HASHTAG_LINE.match(raw):
        return None
    return re.findall(r"#([\w-]+)", raw, flags=re.IGNORECASE)


def _hashtag_command(text: str) -> RoutedMessage | None:
    """Composable operator hashtags → single DATA mode with token tuple."""
    tokens = _extract_hashtag_tokens(text)
    if not tokens:
        return None
    return RoutedMessage("data", "", data_mode="hashtag_composed", hashtag_tokens=tuple(tokens))


def route_message(text: str) -> RoutedMessage:
    """
    Phase 4.6.3 — silo ownership (no @ prefix):
    - Trading / market / risk / concepts → Anna (default front door).
    - DB / system / status / report / insights / infra / connectivity cues → DATA.
    - Engineering / repo / code / architecture (clear cues only) → Cody.
    - Ambiguous → Anna (spokesperson), not Cody.
    Explicit: @anna @data @cody @mia (Mia reserved).
    """
    raw = (text or "").strip()
    tagged = _hashtag_command(raw)
    if tagged is not None:
        return tagged

    low = _norm_phrase(raw)

    intent = _identity_intent_from_text(raw)
    if intent is not None:
        return RoutedMessage("identity", intent)

    if low == "report":
        return RoutedMessage("data", "", data_mode="report")
    if low == "insights":
        return RoutedMessage("data", "", data_mode="insights")
    if low == "status":
        return RoutedMessage("data", "", data_mode="status")
    if low == "infra":
        return RoutedMessage("data", "", data_mode="infra")

    # Natural language (no @ prefix): classify DATA vs Cody before default Anna.
    if not raw.startswith("@"):
        dm = _nl_data_mode(raw)
        if dm is not None:
            return RoutedMessage("data", raw, data_mode=dm)
        if _nl_looks_like_cody(raw):
            return RoutedMessage("cody", raw)

    m_anna = re.match(r"^@anna\s*(.*)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if m_anna:
        rest = (m_anna.group(1) or "").strip()
        sub = _identity_intent_from_text(rest)
        if sub is not None:
            return RoutedMessage("identity", sub)
        if not rest.startswith("@"):
            dm = _nl_data_mode(rest)
            if dm is not None:
                return RoutedMessage("data", rest, data_mode=dm)
            if _nl_looks_like_cody(rest):
                return RoutedMessage("cody", rest)
        return RoutedMessage("anna", rest if rest else raw)

    m_data = re.match(r"^@data\s*(.*)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if m_data:
        rest = m_data.group(1) or ""
        mode, body = _parse_data_remainder(rest)
        return RoutedMessage("data", body, data_mode=mode)

    m_mia = re.match(r"^@mia\s*(.*)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if m_mia:
        rest = (m_mia.group(1) or "").strip()
        return RoutedMessage("mia", rest)

    m_cody = re.match(r"^@cody\s*(.*)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if m_cody:
        rest = (m_cody.group(1) or "").strip()
        return RoutedMessage("cody", rest if rest else "What would you like to improve or explore?")

    if low == "cody":
        return RoutedMessage("cody", "What would you like to improve or explore?")

    cm = _CODY_LEAD.match(raw)
    if cm:
        return RoutedMessage("cody", (cm.group(1) or "").strip() or raw)

    m = re.match(r"^/?anna\s*(.*)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if m:
        remainder = (m.group(1) or "").strip()
        sub = _identity_intent_from_text(remainder)
        if sub is not None:
            return RoutedMessage("identity", sub)
        if not remainder.startswith("@"):
            dm = _nl_data_mode(remainder)
            if dm is not None:
                return RoutedMessage("data", remainder, data_mode=dm)
            if _nl_looks_like_cody(remainder):
                return RoutedMessage("cody", remainder)
        return RoutedMessage("anna", remainder if remainder else raw)

    return RoutedMessage("anna", raw)
