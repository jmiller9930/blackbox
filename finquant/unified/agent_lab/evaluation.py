"""
FinQuant Unified Agent Lab — Evaluation

Grades lifecycle outcomes and produces the result that feeds learning records.

Failure modes tracked:
  entry_quality, no_trade_quality, hold_quality, exit_quality,
  missed_opportunity, premature_exit, late_exit, thesis_failure,
  invalidation_failure, indicator_misuse, regime_misread, risk_reward_failure
"""

from __future__ import annotations
from typing import Any


def evaluate_lifecycle(
    case: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Grade decisions against the case outcome and return a result dict."""
    case_id = case["case_id"]
    outcome_candles = case.get("outcome_candles", [])
    expected_behavior = case.get("expected_behavior", {})

    actions_taken = [d["action"] for d in decisions]
    final_action = actions_taken[-1] if actions_taken else None

    failure_modes = _detect_failure_modes(
        actions=actions_taken,
        expected=expected_behavior,
        outcome_candles=outcome_candles,
    )

    grade = _grade(failure_modes=failure_modes, expected=expected_behavior, actions=actions_taken)

    leakage_clean = _audit_leakage(decisions=decisions, case=case)

    return {
        "case_id": case_id,
        "actions_taken": actions_taken,
        "final_action": final_action,
        "step_decisions_emitted": len(decisions),
        "final_action_resolved": final_action is not None,
        "failure_modes": failure_modes,
        "grade_v1": grade,
        "leakage_audit": {"pass": leakage_clean},
        "pass": grade == "PASS" and leakage_clean,
    }


def _detect_failure_modes(
    actions: list[str],
    expected: dict,
    outcome_candles: list,
) -> list[str]:
    """Stub: return empty list in scaffold phase. Implement grading logic here."""
    return []


def _grade(failure_modes: list[str], expected: dict, actions: list[str]) -> str:
    """Stub grader: PASS if no failure modes detected."""
    if failure_modes:
        return "FAIL"
    return "PASS"


def _audit_leakage(decisions: list[dict], case: dict) -> bool:
    """Verify no decision references future candle data.

    In scaffold phase: always passes (no LLM output to inspect).
    Full implementation must parse decision.thesis for future bar references.
    """
    for d in decisions:
        if not d.get("causal_context_only_v1", True):
            return False
    return True
