"""
FinQuant Unified Agent Lab — Decision Contracts

Enforces finquant_decision_v1 schema.
FinQuant owns the decision contract. The LLM does not write decisions directly.
All LLM output must be converted here before it is treated as an agent decision.
"""

from __future__ import annotations
from typing import Any

VALID_ACTIONS = {"NO_TRADE", "ENTER_LONG", "ENTER_SHORT", "HOLD", "EXIT"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_DECISION_SOURCE = {"rule", "llm", "hybrid"}

DECISION_SCHEMA = "finquant_decision_v1"


def make_decision(
    *,
    case_id: str,
    step_index: int,
    symbol: str,
    action: str,
    thesis: str,
    invalidation: str,
    confidence_band: str = "low",
    supporting_indicators: list | None = None,
    conflicting_indicators: list | None = None,
    risk_notes: str = "",
    memory_used_v1: list | None = None,
    llm_used_v1: bool = False,
    decision_source_v1: str = "rule",
    causal_context_only_v1: bool = True,
) -> dict[str, Any]:
    decision = {
        "schema": DECISION_SCHEMA,
        "agent_id": "finquant",
        "case_id": case_id,
        "step_index": step_index,
        "symbol": symbol,
        "action": action,
        "thesis": thesis,
        "invalidation": invalidation,
        "confidence_band": confidence_band,
        "supporting_indicators": supporting_indicators or [],
        "conflicting_indicators": conflicting_indicators or [],
        "risk_notes": risk_notes,
        "memory_used_v1": memory_used_v1 or [],
        "llm_used_v1": llm_used_v1,
        "decision_source_v1": decision_source_v1,
        "causal_context_only_v1": causal_context_only_v1,
    }
    validate_decision(decision)
    return decision


def validate_decision(decision: dict[str, Any]) -> None:
    if decision.get("schema") != DECISION_SCHEMA:
        raise ValueError(f"decision schema must be '{DECISION_SCHEMA}'")
    if decision.get("action") not in VALID_ACTIONS:
        raise ValueError(f"invalid action '{decision.get('action')}'; must be one of {VALID_ACTIONS}")
    if decision.get("confidence_band") not in VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence_band '{decision.get('confidence_band')}'")
    if decision.get("decision_source_v1") not in VALID_DECISION_SOURCE:
        raise ValueError(f"invalid decision_source_v1 '{decision.get('decision_source_v1')}'")
