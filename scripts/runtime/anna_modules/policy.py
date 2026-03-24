"""
Policy alignment: guardrail mode, alignment vs suggested intent, paper-only suggested_action.
"""
from __future__ import annotations

import re
from typing import Any

from anna_modules.input_adapter import guardrail_mode_from_policy


def build_suggested_action(
    *,
    guardrail_mode: str,
    risk_level: str,
    input_text: str,
) -> dict[str, Any]:
    neg = re.search(r"\b(thin|crash|panic|liquidat|unsafe|avoid|stop\s*hunt)\b", input_text, re.I)
    intent = "WATCH"
    conf = "medium"
    rationale = "Default cautious stance without full policy/market context."

    if guardrail_mode == "FROZEN":
        intent, conf = "HOLD", "low"
        rationale = "Policy mode FROZEN: stand down from new risk; paper rehearsal only if explicitly gated elsewhere."
    elif guardrail_mode == "CAUTION":
        intent, conf = "WATCH", "medium"
        rationale = "Policy mode CAUTION: monitor and size conservatively; no execution implied."
    elif guardrail_mode == "NORMAL":
        if neg or risk_level == "high":
            intent, conf = "WATCH", "medium"
            rationale = "NORMAL policy but language or signals warrant monitoring before any paper rehearsal."
        else:
            intent, conf = "PAPER_TRADE_READY", "low"
            rationale = (
                "Policy mode NORMAL and no strong caution signals in text/context; "
                "paper path only — still no live execution."
            )
    else:
        intent, conf = "WATCH", "low"
        rationale = (
            "No live guardrail policy is attached in this session; stay cautious and paper-only — "
            "no execution implied."
        )

    return {"intent": intent, "confidence": conf, "rationale": rationale}


def compute_alignment(guardrail_mode: str, intent: str, input_text: str) -> str:
    neg = re.search(r"\b(thin|crash|panic|liquidat|unsafe|avoid|stop\s*hunt)\b", input_text, re.I)
    alignment = "unknown"
    if guardrail_mode == "unknown":
        alignment = "unknown"
    elif guardrail_mode == "FROZEN":
        alignment = "aligned" if intent == "HOLD" else "misaligned"
    elif guardrail_mode == "CAUTION":
        alignment = "aligned" if intent in ("HOLD", "WATCH") else "cautious"
    elif guardrail_mode == "NORMAL":
        if intent == "PAPER_TRADE_READY" and neg:
            alignment = "cautious"
        elif intent == "PAPER_TRADE_READY":
            alignment = "aligned"
        else:
            alignment = "aligned"
    return alignment


def policy_notes(policy: dict[str, Any] | None) -> list[str]:
    if policy:
        return [f"Policy reasoning (excerpt): {(policy.get('reasoning') or '')[:280]}"]
    return ["No guardrail policy document loaded."]


def build_policy_alignment_dict(
    policy: dict[str, Any] | None,
    intent: str,
    input_text: str,
) -> dict[str, Any]:
    gm = guardrail_mode_from_policy(policy)
    return {
        "guardrail_mode": gm,
        "alignment": compute_alignment(gm, intent, input_text),
        "notes": policy_notes(policy),
    }
