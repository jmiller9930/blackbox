"""
GT_DIRECTIVE_026AI — per-run / per-trade token and dollar budget enforcement (no hard crash).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_SNAPSHOT = "reasoning_cost_governor_snapshot_v1"
CONTRACT_VERSION = 1


@dataclass
class ReasoningCostGovernorV1:
    """Mutable state for a single Student run (or test harness)."""

    max_external_calls_per_run: int = 1
    max_external_calls_per_trade: int = 1
    max_input_tokens_per_call: int = 8000
    max_output_tokens_per_call: int = 2000
    max_total_tokens_per_run: int = 24_000
    max_estimated_cost_usd_per_run: float = 0.5
    external_calls_this_run: int = 0
    external_calls_this_trade: int = 0
    total_tokens_this_run: int = 0
    estimated_cost_usd_this_run: float = 0.0
    trace_rows_v1: list[dict[str, Any]] = field(default_factory=list)

    def can_attempt_external(
        self,
        *,
        estimated_input_tokens: int,
        estimated_output_cap: int,
    ) -> tuple[bool, str | None, list[str]]:
        """
        Returns ``(allowed, primary_blocker_code, reason_codes)``.
        Blocker codes use ``allowed blockers`` vocabulary for router.
        """
        rcs: list[str] = []
        if self.external_calls_this_run >= self.max_external_calls_per_run:
            return False, "budget_exceeded_v1", rcs + ["run_call_cap"]
        if self.external_calls_this_trade >= self.max_external_calls_per_trade:
            return False, "budget_exceeded_v1", rcs + ["trade_call_cap"]
        est = int(estimated_input_tokens) + int(estimated_output_cap)
        if estimated_input_tokens > self.max_input_tokens_per_call:
            return False, "token_limit_exceeded_v1", rcs + ["input_cap"]
        if estimated_output_cap > self.max_output_tokens_per_call:
            return False, "token_limit_exceeded_v1", rcs + ["output_cap"]
        if self.total_tokens_this_run + est > self.max_total_tokens_per_run:
            return False, "token_limit_exceeded_v1", rcs + ["run_token_cap"]
        if self.estimated_cost_usd_this_run >= self.max_estimated_cost_usd_per_run - 1e-9:
            return False, "budget_exceeded_v1", rcs + ["dollar_cap"]
        return True, None, rcs

    def record_external_result_v1(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        estimated_cost_usd: float,
        record: dict[str, Any],
    ) -> None:
        self.external_calls_this_run += 1
        self.external_calls_this_trade += 1
        self.total_tokens_this_run += int(total_tokens)
        self.estimated_cost_usd_this_run += float(estimated_cost_usd)
        self.trace_rows_v1.append(record)

    def to_snapshot_v1(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_SNAPSHOT,
            "contract_version": CONTRACT_VERSION,
            "external_calls_this_run": self.external_calls_this_run,
            "external_calls_this_trade": self.external_calls_this_trade,
            "total_tokens_this_run": self.total_tokens_this_run,
            "estimated_cost_usd_this_run": round(self.estimated_cost_usd_this_run, 8),
            "max_external_calls_per_run": self.max_external_calls_per_run,
            "max_total_tokens_per_run": self.max_total_tokens_per_run,
            "max_estimated_cost_usd_per_run": self.max_estimated_cost_usd_per_run,
        }
