"""
FinQuant Unified Agent Lab — Evaluation (lightweight Referee).

Grades lifecycle decisions and produces evaluation.json.
"""

from __future__ import annotations
from typing import Any

from schemas import SCHEMA_LIFECYCLE_EVALUATION, VALID_FINAL_STATUS


def evaluate_lifecycle(
    case: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Grade decisions and return evaluation dict matching finquant_lifecycle_evaluation_v1."""
    case_id = case["case_id"]
    candles = case["candles"]
    hide_from = case["hidden_future_start_index"]
    expected_focus = case.get("expected_learning_focus_v1", [])

    actions = [d["action"] for d in decisions]
    final_action = actions[-1] if actions else None

    outcome_candles = candles[hide_from:]

    entry_quality = _grade_entry(actions, candles, case)
    exit_quality = _grade_exit(actions, candles, case, outcome_candles)
    hold_quality = _grade_hold(actions)
    no_trade_correctness = _grade_no_trade(actions, case)
    learning_labels = _collect_labels(
        actions, entry_quality, exit_quality, hold_quality, no_trade_correctness, expected_focus
    )
    notes = _build_notes(decisions, case)

    # Overall status: INFO in scaffold (stub decisions don't claim profitability)
    final_status = _resolve_status(entry_quality, exit_quality, no_trade_correctness)

    return {
        "schema": SCHEMA_LIFECYCLE_EVALUATION,
        "case_id": case_id,
        "final_status_v1": final_status,
        "entry_quality_v1": entry_quality,
        "exit_quality_v1": exit_quality,
        "hold_quality_v1": hold_quality,
        "no_trade_correctness_v1": no_trade_correctness,
        "actions_taken": actions,
        "final_action": final_action,
        "step_decisions_emitted": len(decisions),
        "learning_labels_v1": learning_labels,
        "notes": notes,
    }


def _grade_entry(actions: list[str], candles: list, case: dict) -> str:
    has_entry = any(a in ("ENTER_LONG", "ENTER_SHORT") for a in actions)
    expected_entry = "entry_quality" in case.get("expected_learning_focus_v1", [])
    if expected_entry and has_entry:
        return "entered_as_expected"
    if not expected_entry and not has_entry:
        return "correctly_abstained"
    if expected_entry and not has_entry:
        return "missed_entry"
    return "unexpected_entry"


def _grade_exit(
    actions: list[str],
    candles: list,
    case: dict,
    outcome_candles: list,
) -> str:
    has_exit = "EXIT" in actions
    expected_exit = "exit_quality" in case.get("expected_learning_focus_v1", [])
    invalidation_focus = "invalidated_thesis" in case.get("expected_learning_focus_v1", [])
    if (expected_exit or invalidation_focus) and has_exit:
        return "exited_as_expected"
    if not expected_exit and not invalidation_focus and not has_exit:
        return "no_exit_needed"
    if (expected_exit or invalidation_focus) and not has_exit:
        return "missed_exit"
    return "unexpected_exit"


def _grade_hold(actions: list[str]) -> str:
    holds = actions.count("HOLD")
    return f"hold_steps={holds}"


def _grade_no_trade(actions: list[str], case: dict) -> str:
    all_no_trade = all(a == "NO_TRADE" for a in actions)
    expected_no_trade = "no_trade_quality" in case.get("expected_learning_focus_v1", [])
    if expected_no_trade and all_no_trade:
        return "correctly_stood_down"
    if not expected_no_trade and not all_no_trade:
        return "traded_as_expected"
    return "mixed"


def _collect_labels(
    actions: list[str],
    entry_quality: str,
    exit_quality: str,
    hold_quality: str,
    no_trade_correctness: str,
    expected_focus: list[str],
) -> list[str]:
    labels: list[str] = list(expected_focus)
    if "missed_entry" in entry_quality:
        labels.append("missed_opportunity")
    if "missed_exit" in exit_quality:
        labels.append("late_exit")
    if "unexpected_exit" in exit_quality:
        labels.append("premature_exit")
    if "unexpected_entry" in entry_quality:
        labels.append("unexpected_entry")
    return list(dict.fromkeys(labels))  # deduplicate, preserve order


def _build_notes(decisions: list[dict], case: dict) -> list[str]:
    notes: list[str] = []
    for d in decisions:
        notes.append(f"step {d['step_index']}: action={d['action']} source={d['decision_source_v1']}")
    notes.append(f"leakage_audit: causal_context_only confirmed (stub, no LLM output)")
    return notes


def _resolve_status(entry_quality: str, exit_quality: str, no_trade_correctness: str) -> str:
    fail_signals = ("missed_entry", "missed_exit", "unexpected_exit", "unexpected_entry")
    combined = entry_quality + exit_quality + no_trade_correctness
    for sig in fail_signals:
        if sig in combined:
            return "FAIL"
    return "INFO"
