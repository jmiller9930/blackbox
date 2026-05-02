"""
FinQuant Unified Agent Lab — learning governance.

Determines whether a lifecycle outcome becomes a retrievable lesson.
"""

from __future__ import annotations

from typing import Any


def build_learning_governance(
    *,
    evaluation: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    status = str(evaluation.get("final_status_v1") or "INFO")
    labels = list(evaluation.get("learning_labels_v1") or [])
    actions = [str(d.get("action") or "") for d in decisions]
    has_trade = any(a in {"ENTER_LONG", "ENTER_SHORT"} for a in actions)

    promotable = (
        status != "FAIL"
        and "unexpected_entry" not in labels
        and "late_exit" not in labels
        and "premature_exit" not in labels
    )
    if promotable:
        decision = "PROMOTE"
        reason_codes = ["promote_clean_lifecycle_v1"]
        if not has_trade:
            reason_codes.append("promote_no_trade_discipline_v1")
    else:
        decision = "REJECT"
        reason_codes = ["reject_failed_or_unstable_v1"]
        if status == "FAIL":
            reason_codes.append("reject_final_status_fail_v1")
        reason_codes.extend(labels)

    return {
        "decision": decision,
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }


def build_lesson_text(
    *,
    case: dict[str, Any],
    evaluation: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> str:
    first = decisions[0] if decisions else {}
    final_action = str(evaluation.get("final_action") or "NO_TRADE")
    return (
        f"Case {case.get('case_id')} on {case.get('symbol')} ended with "
        f"{evaluation.get('final_status_v1')} after final_action={final_action}. "
        f"Initial thesis: {str(first.get('thesis_v1') or '').strip() or 'n/a'}"
    )[:1000]
