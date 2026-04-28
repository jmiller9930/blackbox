"""
Ask DATA **intent router** — selects which Ollama **tier** (host + model) should answer.

**No mutations:** routing only affects **read / explain** generation. Tool execution stays elsewhere.

Tiers
-----

* **pml_lightweight** — default: fast glossary + run/scorecard Q&A (``qwen2.5:7b`` on PML host).
* **system_agent** — structured / schema / API / workflow wording (``qwen3-coder:30b`` on System Agent host).
* **deepseek_escalation** — explicit debug / deep reasoning (default ``deepseek-r1:14b`` on escalation host ``172.20.2.230`` unless ``DEEPSEEK_ESCALATION_OLLAMA_MODEL`` overrides).

Disable router (always lightweight LLM): ``ASK_DATA_ROUTER=0``.
Force tier (operator override): ``ASK_DATA_ROUTE=lightweight|system_agent|deepseek`` (aliases: ``pml``, ``agent``, ``deep``, ``deepseek_escalation``).
"""

from __future__ import annotations

import os
import re
from typing import Literal

AskDataRouteTier = Literal["pml_lightweight", "system_agent", "deepseek_escalation"]

_FORCE = re.compile(r"^\s*\[(debug|escalation|deep)\]\s*", re.I)
_SYSTEM_HINT = re.compile(
    r"(?i)\b("
    r"sql\b|json\s*schema|yaml\b|xml\b|openapi|"
    r"validate\s+(this|the)\s+json|"
    r"api\s+route|http\s+endpoint|endpoint\s+list|"
    r"propose\s+(a|the)\s+(change|patch|migration)|"
    r"tool\s*(-driven)?\s+workflow|"
    r"refactor\s+(the|this)\s+code|"
    r"write\s+(a|the)\s+query\b|"
    r"memory\s+fusion|fusion\s+policy"
    r")\b"
)

_DEEP_HINT = re.compile(
    r"(?i)("
    r"\bprove\b.{0,240}?\boptimal\b|"
    r"\bformal\s+proof\b|"
    r"\bexhaustive\s+(state|search)\s+space\b"
    r")"
)


def ask_data_router_enabled_v1() -> bool:
    v = os.environ.get("ASK_DATA_ROUTER")
    if v is None or str(v).strip() == "":
        return True
    return str(v).strip().lower() not in ("0", "false", "no", "off")


def classify_ask_data_route_v1(question: str) -> AskDataRouteTier:
    """Rule-based classifier (no extra LLM call). Conservative: default lightweight."""
    forced = (os.environ.get("ASK_DATA_ROUTE") or "").strip().lower()
    if forced in ("lightweight", "pml", "pml_lightweight", "fast"):
        return "pml_lightweight"
    if forced in ("system_agent", "agent", "coder", "strong"):
        return "system_agent"
    if forced in ("deepseek", "escalation", "debug", "deep", "deepseek_escalation"):
        return "deepseek_escalation"

    if not ask_data_router_enabled_v1():
        return "pml_lightweight"

    q = (question or "").strip()
    if not q:
        return "pml_lightweight"
    if _FORCE.search(q):
        return "deepseek_escalation"
    ql = q.lower()
    if "escalation:" in ql or "deep dive diagnostic" in ql:
        return "deepseek_escalation"
    if len(q) > 4000:
        return "system_agent"
    if _SYSTEM_HINT.search(q):
        return "system_agent"
    if _DEEP_HINT.search(q):
        return "deepseek_escalation"
    return "pml_lightweight"


def ask_data_ollama_target_for_route_v1(route: AskDataRouteTier) -> tuple[str, str, float]:
    """Return ``(base_url, model, timeout_sec)`` for the tier."""
    from renaissance_v4.game_theory.ollama_role_routing_v1 import (
        deepseek_escalation_ollama_base_url,
        deepseek_escalation_ollama_model,
        pml_lightweight_ollama_base_url,
        pml_lightweight_ollama_model,
        system_agent_ollama_base_url,
        system_agent_ollama_model_primary,
    )

    if route == "deepseek_escalation":
        return (
            deepseek_escalation_ollama_base_url(),
            deepseek_escalation_ollama_model(),
            float(os.environ.get("ASK_DATA_OLLAMA_TIMEOUT_DEEPSEEK", "240") or 240),
        )
    if route == "system_agent":
        return (
            system_agent_ollama_base_url(),
            system_agent_ollama_model_primary(),
            float(os.environ.get("ASK_DATA_OLLAMA_TIMEOUT_SYSTEM_AGENT", "180") or 180),
        )
    return (
        pml_lightweight_ollama_base_url(),
        pml_lightweight_ollama_model(),
        float(os.environ.get("ASK_DATA_OLLAMA_TIMEOUT_LIGHTWEIGHT", "120") or 120),
    )


__all__ = [
    "AskDataRouteTier",
    "ask_data_ollama_target_for_route_v1",
    "ask_data_router_enabled_v1",
    "classify_ask_data_route_v1",
]
