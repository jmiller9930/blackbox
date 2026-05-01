"""
FinQuant Unified Agent Lab — Lifecycle Engine

Steps through case candles one at a time (no lookahead).
Emits finquant_decision_v1 objects at each step.

Phase 0: rule-based stub decisions. LLM wiring is a later phase.
"""

from __future__ import annotations
from typing import Any

from decision_contracts import make_decision


class LifecycleEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def run_case(
        self,
        case: dict[str, Any],
        prior_records: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """Process all steps in a case, returning one decision per step."""
        case_id = case["case_id"]
        symbol = case["symbol"]
        steps = case["steps"]
        decisions: list[dict[str, Any]] = []

        position_open = False

        for i, step in enumerate(steps):
            visible_bars = step.get("visible_bars", [])
            indicators = step.get("indicators", {})

            action, thesis, invalidation = self._decide(
                step_index=i,
                visible_bars=visible_bars,
                indicators=indicators,
                position_open=position_open,
                prior_records=prior_records or [],
            )

            decision = make_decision(
                case_id=case_id,
                step_index=i,
                symbol=symbol,
                action=action,
                thesis=thesis,
                invalidation=invalidation,
                confidence_band="low",
                decision_source_v1="rule",
                causal_context_only_v1=True,
            )
            decisions.append(decision)

            if action in ("ENTER_LONG", "ENTER_SHORT"):
                position_open = True
            elif action == "EXIT":
                position_open = False

        return decisions

    def _decide(
        self,
        step_index: int,
        visible_bars: list,
        indicators: dict,
        position_open: bool,
        prior_records: list,
    ) -> tuple[str, str, str]:
        """Stub rule-based decision logic. Replace with LLM call in later phase."""
        if not visible_bars:
            return (
                "NO_TRADE",
                "No candle data visible at this step.",
                "Insufficient data.",
            )

        if position_open:
            return (
                "HOLD",
                "Position open; monitoring for exit condition.",
                "Exit if thesis invalidates.",
            )

        # Stub: always NO_TRADE in scaffold phase
        return (
            "NO_TRADE",
            "Scaffold stub: no entry conditions evaluated yet.",
            "Scaffold stub: no invalidation logic yet.",
        )
