"""
FinQuant Unified Agent Lab — Decision Contracts

FinQuant owns the decision contract. The LLM does not write decisions directly.
All model or rule output must be normalized here before it is treated as an
agent decision.
"""

from __future__ import annotations
from typing import Any

from schemas import SCHEMA_LIFECYCLE_DECISION, VALID_ACTIONS

VALID_ACTIONS = {"NO_TRADE", "ENTER_LONG", "ENTER_SHORT", "HOLD", "EXIT"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_DECISION_SOURCE = {"deterministic_stub_v1", "rule", "llm", "hybrid"}

DECISION_SCHEMA = SCHEMA_LIFECYCLE_DECISION


def make_decision(
    *,
    case_id: str,
    step_index: int,
    symbol: str,
    action: str,
    thesis_v1: str,
    invalidation_v1: str,
    risk_state_v1: str = "undefined",
    observed_context_v1: dict | None = None,
    input_packet_v1: dict | None = None,
    confidence_band_v1: str = "low",
    supporting_indicators_v1: list | None = None,
    conflicting_indicators_v1: list | None = None,
    risk_notes_v1: str = "",
    memory_used_v1: list | None = None,
    llm_used_v1: bool = False,
    decision_source_v1: str = "deterministic_stub_v1",
    causal_context_only_v1: bool = True,
) -> dict[str, Any]:
    decision = {
        "schema": DECISION_SCHEMA,
        "agent_id": "finquant",
        "case_id": case_id,
        "step_index": step_index,
        "symbol": symbol,
        "action": action,
        "thesis_v1": thesis_v1,
        "invalidation_v1": invalidation_v1,
        "risk_state_v1": risk_state_v1,
        "observed_context_v1": observed_context_v1 or {},
        "input_packet_v1": input_packet_v1 or {},
        "confidence_band_v1": confidence_band_v1,
        "supporting_indicators_v1": supporting_indicators_v1 or [],
        "conflicting_indicators_v1": conflicting_indicators_v1 or [],
        "risk_notes_v1": risk_notes_v1,
        "memory_used_v1": memory_used_v1 or [],
        "llm_used_v1": llm_used_v1,
        "decision_source_v1": decision_source_v1,
        "causal_context_only_v1": causal_context_only_v1,
    }
    # Backward-compatible aliases for older tooling and ad hoc inspection.
    decision["thesis"] = decision["thesis_v1"]
    decision["invalidation"] = decision["invalidation_v1"]
    decision["confidence_band"] = decision["confidence_band_v1"]
    decision["supporting_indicators"] = list(decision["supporting_indicators_v1"])
    decision["conflicting_indicators"] = list(decision["conflicting_indicators_v1"])
    decision["risk_notes"] = decision["risk_notes_v1"]
    validate_decision(decision)
    return decision


def validate_decision(decision: dict[str, Any]) -> None:
    if decision.get("schema") != DECISION_SCHEMA:
        raise ValueError(f"decision schema must be '{DECISION_SCHEMA}'")
    if decision.get("action") not in VALID_ACTIONS:
        raise ValueError(f"invalid action '{decision.get('action')}'; must be one of {VALID_ACTIONS}")
    if decision.get("confidence_band_v1") not in VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence_band_v1 '{decision.get('confidence_band_v1')}'")
    if decision.get("decision_source_v1") not in VALID_DECISION_SOURCE:
        raise ValueError(f"invalid decision_source_v1 '{decision.get('decision_source_v1')}'")
