"""
Proposal shaping: anna_analysis_v1 → anna_proposal_v1 (validation-loop bridge).
"""
from __future__ import annotations

import os
import re
from typing import Any

from anna_modules.util import PROPOSAL_SCHEMA_VERSION, utc_now

PROPOSAL_TYPES = ("NO_CHANGE", "RISK_REDUCTION", "CONDITION_TIGHTENING", "OBSERVATION_ONLY")


def classify_proposal_type(anna: dict[str, Any]) -> str:
    pol = anna.get("policy_alignment") or {}
    mode = pol.get("guardrail_mode") or "unknown"
    risk = (anna.get("risk_assessment") or {}).get("level") or "low"
    intent = (anna.get("suggested_action") or {}).get("intent") or "WATCH"
    concepts = list(anna.get("concepts_used") or [])
    text = anna.get("input_text") or ""
    confirm_need = re.search(
        r"\b(confirm|confirmation|wait|unsure|ambiguous|more data|need more)\b", text, re.I
    )

    if not concepts and mode == "unknown" and risk == "low":
        return "OBSERVATION_ONLY"

    if mode == "FROZEN" or intent == "HOLD" or risk == "high":
        return "RISK_REDUCTION"

    if mode == "CAUTION" or (intent == "WATCH" and risk in ("medium", "high")) or confirm_need:
        return "CONDITION_TIGHTENING"

    if mode == "NORMAL" and risk == "low" and intent == "PAPER_TRADE_READY" and not confirm_need:
        return "NO_CHANGE"

    if mode == "unknown" or risk == "low":
        return "OBSERVATION_ONLY"

    return "CONDITION_TIGHTENING"


def _lab_wire_jack_override(ptype: str) -> str:
    """Karpathy lab: OBSERVATION_ONLY never creates execution_request → Jack never runs.

    Set ``ANNA_KARPATHY_LAB_WIRE_JACK=1`` to map OBSERVATION_ONLY → CONDITION_TIGHTENING so the
    harness can still build a pending request (subject to ``BLACKBOX_JACK_EXECUTOR_CMD``, etc.).
    """
    if ptype != "OBSERVATION_ONLY":
        return ptype
    if (os.environ.get("ANNA_KARPATHY_LAB_WIRE_JACK") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        return ptype
    return "CONDITION_TIGHTENING"


def paper_intent_for_proposal(proposal_type: str, anna_intent: str) -> str:
    if proposal_type == "NO_CHANGE":
        return "unchanged"
    if proposal_type == "OBSERVATION_ONLY":
        return "unknown"
    return anna_intent if anna_intent in ("HOLD", "WATCH", "PAPER_TRADE_READY") else "unknown"


def build_anna_proposal(
    anna: dict[str, Any],
    *,
    source_task_id: str | None,
    extra_notes: list[str],
) -> dict[str, Any]:
    ptype = _lab_wire_jack_override(classify_proposal_type(anna))
    pol = anna.get("policy_alignment") or {}
    mode = pol.get("guardrail_mode") or "unknown"
    risk = (anna.get("risk_assessment") or {}).get("level") or "unknown"
    alignment = pol.get("alignment") or "unknown"
    intent = (anna.get("suggested_action") or {}).get("intent") or "WATCH"
    interp = (anna.get("interpretation") or {}).get("summary") or ""
    concepts = list(anna.get("concepts_used") or [])

    paper_intent = paper_intent_for_proposal(ptype, intent)

    guardrail_interaction = (
        f"Proposal derived under guardrail posture {mode}. "
        f"Type {ptype}: align Anna interpretation with paper-only evaluation and later outcome checks — not execution."
    )

    reasoning_scope = ["risk", "market_conditions"]
    if concepts:
        reasoning_scope.append("execution_quality")

    summary = (
        f"{ptype}: Anna recommends structuring follow-up as {ptype.lower().replace('_', ' ')} "
        f"based on trader input, risk {risk}, and policy {mode}."
    )

    validation_plan = {
        "what_to_watch": [
            "Paper pipeline outcomes and guardrail mode stability after this interpretation.",
            "Whether market_context fields (if present) evolve consistently with the stated concern.",
        ],
        "success_signals": [
            "Later insights/trends show reduced misalignment or stable readiness when proposal was observational.",
            "Recorded reflections cite this proposal when explaining a cautious or no-change decision.",
        ],
        "failure_signals": [
            "Outcomes contradict the stated risk posture without documented reason.",
            "Repeated failures while policy remained unchanged despite RISK_REDUCTION proposal.",
        ],
    }
    if ptype == "RISK_REDUCTION":
        validation_plan["what_to_watch"].insert(
            0, "Elevated risk factors and FROZEN/CAUTION persistence in guardrail policy."
        )
    elif ptype == "CONDITION_TIGHTENING":
        validation_plan["what_to_watch"].insert(
            0, "Conditions that must improve before increasing paper exposure."
        )

    caution = list(anna.get("caution_flags") or [])
    caution.append("anna_proposal_v1 is not an order; compare later to paper outcomes and reflections.")

    notes = list(extra_notes)
    notes.append(
        "Prepared for later comparison to paper outcomes, reflections, insights, and trends — automated diff not implemented in this phase."
    )

    execution_context = {
        "regime": anna.get("regime"),
        "signal_snapshot": anna.get("signal_snapshot"),
    }

    return {
        "kind": "anna_proposal_v1",
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source_analysis_reference": {
            "task_id": source_task_id,
            "kind": "anna_analysis_v1",
        },
        "execution_context": execution_context,
        "proposal_type": ptype,
        "proposal_summary": summary,
        "proposed_effect": {
            "paper_mode_intent": paper_intent,
            "guardrail_interaction": guardrail_interaction,
            "reasoning_scope": reasoning_scope,
        },
        "validation_plan": validation_plan,
        "supporting_reasoning": {
            "interpretation_summary": interp,
            "risk_level": risk,
            "policy_alignment": f"guardrail_mode={mode}, alignment={alignment}",
            "concepts_used": concepts,
        },
        "caution_flags": caution[:16],
        "notes": notes,
    }


assemble_anna_proposal_v1 = build_anna_proposal
