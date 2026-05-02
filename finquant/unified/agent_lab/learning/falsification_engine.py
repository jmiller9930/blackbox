"""
FinQuant — Falsification Engine

Turns "what happened" into a verdict: confirmed, rejected, or inconclusive.

Inputs:
  - The proposed action and hypothesis embedded in the learning unit
  - The actual lifecycle outcome from evaluation.py
  - The candle set (visible at decision time vs the outcome candles)

The engine is intentionally strict:
  - confirmed = expectation met AND invalidation NOT triggered
  - rejected  = invalidation condition matched
  - inconclusive = neither happened (ambiguous outcome)

Inconclusive observations matter:
  they don't move confidence but they age the unit and can be a competition
  tie-break.
"""

from __future__ import annotations

from typing import Any


def _outcome_close_change(case: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return (entry_close, last_outcome_close)."""
    candles = case.get("candles") or []
    hide_from = int(case.get("hidden_future_start_index", 0) or 0)
    if hide_from <= 0 or hide_from > len(candles):
        return None, None

    entry = candles[hide_from - 1].get("close")
    if not candles[hide_from:]:
        return entry, entry
    last_outcome = candles[-1].get("close")
    return float(entry) if entry is not None else None, float(last_outcome) if last_outcome is not None else None


def falsify(
    *,
    proposed_action: str,
    case: dict[str, Any],
    evaluation: dict[str, Any],
    actions_taken: list[str],
) -> dict[str, Any]:
    """
    Return a verdict dict:

    {
      "verdict_v1": "confirmed" | "rejected" | "inconclusive",
      "verdict_reason_v1": "<plain text>",
      "actual_outcome_v1": {...},
      "expectation_met_v1": True/False,
      "invalidation_triggered_v1": True/False
    }
    """
    entry_close, last_close = _outcome_close_change(case)
    final_status = str(evaluation.get("final_status_v1", "INFO"))
    entry_quality = str(evaluation.get("entry_quality_v1", ""))
    no_trade_correctness = str(evaluation.get("no_trade_correctness_v1", ""))

    actions_taken = actions_taken or []
    actually_entered = any(a in {"ENTER_LONG", "ENTER_SHORT"} for a in actions_taken)
    actually_exited = "EXIT" in actions_taken
    actually_no_trade = all(a == "NO_TRADE" for a in actions_taken) if actions_taken else False

    actual_outcome = {
        "final_status_v1": final_status,
        "entry_quality_v1": entry_quality,
        "no_trade_correctness_v1": no_trade_correctness,
        "actions_taken_v1": list(actions_taken),
        "entry_close_v1": entry_close,
        "last_outcome_close_v1": last_close,
        "price_change_v1": (
            round(last_close - entry_close, 6)
            if entry_close is not None and last_close is not None
            else None
        ),
    }

    # ---------- Action-specific falsification ----------

    if proposed_action == "NO_TRADE":
        # Confirmed if the case did not need a trade and student abstained
        if actually_no_trade and final_status != "FAIL":
            return _verdict(
                "confirmed",
                "Stand-down was correct: student did not trade and case did not penalize.",
                actual_outcome,
                expectation_met=True,
                invalidation_triggered=False,
            )
        if actually_entered and entry_quality == "unexpected_entry":
            return _verdict(
                "rejected",
                "NO_TRADE proposed but student entered against expectation.",
                actual_outcome,
                expectation_met=False,
                invalidation_triggered=True,
            )
        return _verdict(
            "inconclusive",
            "NO_TRADE proposed but case outcome is mixed.",
            actual_outcome,
            expectation_met=False,
            invalidation_triggered=False,
        )

    if proposed_action == "ENTER_LONG":
        # Expectation: entry was correct AND price moved up after decision
        price_up = (
            entry_close is not None
            and last_close is not None
            and last_close > entry_close * 1.001
        )
        price_down = (
            entry_close is not None
            and last_close is not None
            and last_close < entry_close * 0.997
        )
        if actually_entered and final_status == "PASS" and price_up:
            return _verdict(
                "confirmed",
                "Long entry validated by case PASS and rising price after decision.",
                actual_outcome,
                expectation_met=True,
                invalidation_triggered=False,
            )
        if actually_entered and (final_status == "FAIL" or price_down):
            return _verdict(
                "rejected",
                "Long entry invalidated: case FAILED or price fell after entry.",
                actual_outcome,
                expectation_met=False,
                invalidation_triggered=True,
            )
        if not actually_entered:
            return _verdict(
                "inconclusive",
                "Long was proposed but student did not enter; no evidence to score.",
                actual_outcome,
                expectation_met=False,
                invalidation_triggered=False,
            )
        return _verdict(
            "inconclusive",
            "Long entry occurred but outcome neither clearly confirmed nor rejected.",
            actual_outcome,
            expectation_met=False,
            invalidation_triggered=False,
        )

    if proposed_action == "ENTER_SHORT":
        price_down = (
            entry_close is not None
            and last_close is not None
            and last_close < entry_close * 0.999
        )
        price_up = (
            entry_close is not None
            and last_close is not None
            and last_close > entry_close * 1.003
        )
        if actually_entered and final_status == "PASS" and price_down:
            return _verdict(
                "confirmed",
                "Short entry validated by case PASS and falling price after decision.",
                actual_outcome,
                expectation_met=True,
                invalidation_triggered=False,
            )
        if actually_entered and (final_status == "FAIL" or price_up):
            return _verdict(
                "rejected",
                "Short entry invalidated: case FAILED or price rose after entry.",
                actual_outcome,
                expectation_met=False,
                invalidation_triggered=True,
            )
        return _verdict(
            "inconclusive",
            "Short entry inconclusive.",
            actual_outcome,
            expectation_met=False,
            invalidation_triggered=False,
        )

    if proposed_action in {"HOLD", "EXIT"}:
        if final_status == "PASS":
            return _verdict(
                "confirmed",
                f"{proposed_action} validated by case PASS.",
                actual_outcome,
                expectation_met=True,
                invalidation_triggered=False,
            )
        if final_status == "FAIL":
            return _verdict(
                "rejected",
                f"{proposed_action} invalidated by case FAIL.",
                actual_outcome,
                expectation_met=False,
                invalidation_triggered=True,
            )
        return _verdict(
            "inconclusive",
            f"{proposed_action} outcome ambiguous.",
            actual_outcome,
            expectation_met=False,
            invalidation_triggered=False,
        )

    return _verdict(
        "inconclusive",
        f"No falsification logic for proposed_action={proposed_action!r}.",
        actual_outcome,
        expectation_met=False,
        invalidation_triggered=False,
    )


def _verdict(
    verdict: str,
    reason: str,
    actual_outcome: dict[str, Any],
    *,
    expectation_met: bool,
    invalidation_triggered: bool,
) -> dict[str, Any]:
    return {
        "verdict_v1": verdict,
        "verdict_reason_v1": reason,
        "actual_outcome_v1": actual_outcome,
        "expectation_met_v1": expectation_met,
        "invalidation_triggered_v1": invalidation_triggered,
    }
