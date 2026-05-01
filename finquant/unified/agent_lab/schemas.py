"""
FinQuant Unified Agent Lab — Schema constants and validation helpers.

All schema name constants live here. Modules must import from here — no
hard-coded schema strings scattered across the lab.
"""

from __future__ import annotations
from typing import Any

# ---------------------------------------------------------------------------
# Schema name constants
# ---------------------------------------------------------------------------
SCHEMA_LIFECYCLE_CASE = "finquant_lifecycle_case_v1"
SCHEMA_LIFECYCLE_DECISION = "finquant_lifecycle_decision_v1"
SCHEMA_LIFECYCLE_EVALUATION = "finquant_lifecycle_evaluation_v1"
SCHEMA_LEARNING_RECORD = "finquant_learning_record_v1"
SCHEMA_RETRIEVAL_TRACE = "finquant_retrieval_trace_v1"
SCHEMA_RUN_SUMMARY = "finquant_agent_lab_run_summary_v1"
SCHEMA_CONFIG = "finquant_agent_lab_config_v1"

# ---------------------------------------------------------------------------
# Allowed enum values
# ---------------------------------------------------------------------------
VALID_ACTIONS = {"NO_TRADE", "ENTER_LONG", "ENTER_SHORT", "HOLD", "EXIT"}
VALID_FINAL_STATUS = {"PASS", "FAIL", "INFO"}
VALID_DECISION_SOURCE = {"deterministic_stub_v1", "rule", "llm", "hybrid"}

# ---------------------------------------------------------------------------
# Required case fields
# ---------------------------------------------------------------------------
CASE_REQUIRED_FIELDS = [
    "schema",
    "case_id",
    "symbol",
    "timeframe_minutes",
    "candles",
    "decision_start_index",
    "decision_end_index",
    "hidden_future_start_index",
    "expected_learning_focus_v1",
]

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_case(case: dict[str, Any]) -> None:
    """Raise ValueError if case is missing required fields or has wrong schema."""
    missing = [f for f in CASE_REQUIRED_FIELDS if f not in case]
    if missing:
        raise ValueError(f"case '{case.get('case_id', '?')}' missing fields: {missing}")
    if case["schema"] != SCHEMA_LIFECYCLE_CASE:
        raise ValueError(
            f"case schema must be '{SCHEMA_LIFECYCLE_CASE}', got '{case['schema']}'"
        )
    if not isinstance(case["candles"], list):
        raise ValueError(f"case '{case['case_id']}' candles must be a list")
    n = len(case["candles"])
    for field in ("decision_start_index", "decision_end_index", "hidden_future_start_index"):
        idx = case[field]
        if not (0 <= idx <= n):
            raise ValueError(
                f"case '{case['case_id']}' {field}={idx} out of range [0, {n}]"
            )


def validate_decision(decision: dict[str, Any]) -> None:
    """Raise ValueError if decision has wrong schema or invalid action."""
    if decision.get("schema") != SCHEMA_LIFECYCLE_DECISION:
        raise ValueError(
            f"decision schema must be '{SCHEMA_LIFECYCLE_DECISION}', got '{decision.get('schema')}'"
        )
    action = decision.get("action")
    if action not in VALID_ACTIONS:
        raise ValueError(f"invalid action '{action}'; must be one of {VALID_ACTIONS}")
    source = decision.get("decision_source_v1")
    if source not in VALID_DECISION_SOURCE:
        raise ValueError(f"invalid decision_source_v1 '{source}'")


def make_decision(
    *,
    case_id: str,
    step_index: int,
    symbol: str,
    action: str,
    thesis_v1: str,
    invalidation_v1: str,
    risk_state_v1: str = "undefined",
    confidence_band_v1: str = "low",
    observed_context_v1: dict | None = None,
    memory_used_v1: list | None = None,
    llm_used_v1: bool = False,
    decision_source_v1: str = "deterministic_stub_v1",
    causal_context_only_v1: bool = True,
) -> dict[str, Any]:
    decision = {
        "schema": SCHEMA_LIFECYCLE_DECISION,
        "case_id": case_id,
        "step_index": step_index,
        "symbol": symbol,
        "action": action,
        "thesis_v1": thesis_v1,
        "invalidation_v1": invalidation_v1,
        "risk_state_v1": risk_state_v1,
        "confidence_band_v1": confidence_band_v1,
        "observed_context_v1": observed_context_v1 or {},
        "memory_used_v1": memory_used_v1 or [],
        "llm_used_v1": llm_used_v1,
        "decision_source_v1": decision_source_v1,
        "causal_context_only_v1": causal_context_only_v1,
    }
    validate_decision(decision)
    return decision
