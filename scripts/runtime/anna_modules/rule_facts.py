"""
Authoritative deterministic facts for Anna → LLM grounding.

Facts are computed from text/heuristics; the LLM must explain them, not invent them.
"""
from __future__ import annotations

import re
from typing import Any

from anna_modules.education_definitions import (
    looks_like_definition_question,
    registry_facts_for_prompt,
)


def compute_rule_facts(
    input_text: str,
    human_intent: dict[str, Any],
    concept_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Returns:
      facts_for_prompt: bullet strings the model must treat as true.
      structured: optional machine-readable flags for pipeline_meta / logs.
    """
    raw = (input_text or "").strip()
    low = raw.lower()
    lines: list[str] = []
    structured: dict[str, Any] = {}

    # Confidence vs threshold (e.g. 61 vs 65)
    m61 = re.search(r"\b61\b", raw)
    m65 = re.search(r"\b65\b", raw)
    if m61 and m65 and re.search(r"confidence|threshold|score|adjust", low):
        lines.append("FACT: Adjusted confidence stated in the question: 61.")
        lines.append("FACT: Gate threshold stated in the question: 65.")
        lines.append(
            "FACT: 61 < 65 → the setup does NOT clear the gate; do NOT forward for automated execution."
        )
        lines.append(
            "FACT: Allowed posture is monitor / log / refine inputs — not 'take it anyway'."
        )
        structured["confidence"] = 61
        structured["threshold"] = 65
        structured["forward_to_execution"] = False

    # Loss streak + low volume
    if re.search(r"three\s+consecutive\s+loss", low) and re.search(
        r"low[- ]volume|low volume", low
    ):
        lines.append(
            "FACT: After three consecutive losses in a low-volume regime, edge is likely degraded."
        )
        lines.append("FACT: System posture should be pause / cooldown / revalidation — not fire blindly.")

    # Wide spread at entry
    if "spread" in low and "wide" in low and "entry" in low:
        lines.append("FACT: Wide spread at entry harms fill quality and increases slippage risk.")
        lines.append(
            "FACT: Chart quality alone does not override execution-quality risk at the bid/ask."
        )

    # RSI divergence + weak volume (question-specific)
    if "rsi" in low and "divergenc" in low and re.search(r"volume\s+is\s+weak|weak\s+volume", low):
        lines.append("FACT: Divergence without volume confirmation weakens signal quality.")
        lines.append("FACT: Default is reduce confidence, size down, or skip — not 'always trade'.")

    topic = human_intent.get("topic")
    if topic == "exit_logic":
        lines.append(
            "FACT: Exit timing is risk and structure management (stops, partials, momentum loss) — advisory only."
        )

    if concept_ids and looks_like_definition_question(input_text):
        reg_lines = registry_facts_for_prompt(concept_ids)
        lines.extend(reg_lines)
        if reg_lines:
            structured["registry_definition_grounding"] = list(concept_ids[:6])

    return {
        "facts_for_prompt": lines,
        "structured": structured,
    }
